#!/usr/bin/env python3
"""
repair_failed_batches.py — repair zero-padded embedding batches in-place.

Usage:
    python scripts/repair_failed_batches.py --target "医学纲目:44"
    python scripts/repair_failed_batches.py --target "医学正传:2" --target "辨证录:19"
    python scripts/repair_failed_batches.py --log-file build.log

What it does:
    1. Loads the current FAISS index + metadata.
    2. Locates the latest contiguous segment for each target book title.
    3. Maps batch N -> chunk positions [(N-1)*10, N*10).
    4. Recomputes embeddings only for those chunk positions.
    5. Rebuilds FAISS with repaired vectors, keeping metadata and positions stable.

Notes:
    - It first tries to re-chunk the source book with the fixed chunker.
    - If the new chunk count no longer matches the existing FAISS segment,
      it falls back to repairing from the stored chunk_text in metadata.
    - Oversized stored chunks are split into <= 8000-char pieces and mean-pooled
      into a single replacement vector, so index positions remain unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import os
import pickle
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.core.logger import get_logger, setup_logging
from app.services.chunking_service import chunking_service

setup_logging("INFO")
logger = get_logger(__name__)

TCM_BOOKS_DIR = Path(BACKEND_DIR).parent.parent / "TCM-Ancient-Books-master"
DEFAULT_INDEX_DIR = Path(settings.PROCESSED_DOCUMENTS_DIR) / "faiss_index"
DEFAULT_BATCH_SIZE = 10
EMBED_INPUT_LIMIT = 8000
EMBED_SPLIT_OVERLAP = 200


def _read_file_with_fallback(fpath: str) -> str:
    for enc in ("utf-8", "gb18030", "gbk", "iso-8859-1"):
        try:
            with open(fpath, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""


def _normalize_title_from_path(path: str) -> str:
    title = os.path.splitext(os.path.basename(path))[0]
    return re.sub(r"^\d+-", "", title)


def parse_target(raw: str) -> tuple[str, int]:
    if ":" not in raw:
        raise argparse.ArgumentTypeError(
            f"invalid target '{raw}', expected format '书名:batch'"
        )
    title, batch_str = raw.rsplit(":", 1)
    title = title.strip()
    if not title:
        raise argparse.ArgumentTypeError("book title cannot be empty")
    try:
        batch_no = int(batch_str)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid batch number in '{raw}'"
        ) from exc
    if batch_no <= 0:
        raise argparse.ArgumentTypeError("batch number must be >= 1")
    return title, batch_no


def parse_targets_from_log(log_file: Path) -> list[tuple[str, int]]:
    book_line_re = re.compile(r"Book\s+\d+/\d+.*?—\s*(.*?)\s*—\s*\d+\s+chunks")
    batch_fail_re = re.compile(r"Batch\s+(\d+)\s+(?:retry\s+)?failed:")

    current_title = ""
    found: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()

    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            book_match = book_line_re.search(line)
            if book_match:
                current_title = book_match.group(1).strip()
                continue

            batch_match = batch_fail_re.search(line)
            if batch_match and current_title:
                item = (current_title, int(batch_match.group(1)))
                if item not in seen:
                    seen.add(item)
                    found.append(item)

    return found


def find_book_path(title: str, books_dir: Path) -> Path:
    exact: list[Path] = []
    candidates: list[Path] = []
    for fpath in sorted(glob.glob(str(books_dir / "*.txt"))):
        normalized = _normalize_title_from_path(fpath)
        if normalized == title:
            exact.append(Path(fpath))
        elif title in normalized:
            candidates.append(Path(fpath))

    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ValueError(f"book title '{title}' matched multiple exact files: {exact}")
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(f"book file not found for title '{title}'")
    raise ValueError(f"book title '{title}' matched multiple files: {candidates}")


def rechunk_book(title: str, books_dir: Path) -> list[str]:
    book_path = find_book_path(title, books_dir)
    text = _read_file_with_fallback(str(book_path)).strip()
    if not text:
        raise ValueError(f"book '{title}' could not be read or is empty")
    chunks = chunking_service.chunk_text(text, chunk_size=512, overlap=50)
    return [item["chunk_text"] for item in chunks]


def collect_title_segments(metadata: list[dict], title: str) -> list[tuple[int, int]]:
    segments: list[tuple[int, int]] = []
    start: int | None = None
    for idx, item in enumerate(metadata):
        is_match = item.get("doc_title", "") == title
        if is_match and start is None:
            start = idx
        elif not is_match and start is not None:
            segments.append((start, idx))
            start = None
    if start is not None:
        segments.append((start, len(metadata)))
    return segments


def pick_latest_segment(metadata: list[dict], title: str) -> tuple[int, int]:
    segments = collect_title_segments(metadata, title)
    if not segments:
        raise ValueError(f"book '{title}' not found in FAISS metadata")
    if len(segments) > 1:
        logger.warning(
            "book '%s' appears in %d contiguous segments, repairing the latest one: %s",
            title,
            len(segments),
            segments[-1],
        )
    return segments[-1]


def split_for_embedding(text: str) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= EMBED_INPUT_LIMIT:
        return [cleaned]
    return chunking_service._split_oversized_text(
        cleaned,
        chunk_size=EMBED_INPUT_LIMIT,
        overlap=EMBED_SPLIT_OVERLAP,
    )


async def embed_repair_texts(texts: list[str]) -> np.ndarray:
    from app.integrations.embedding_client import embedding_client

    flat_inputs: list[str] = []
    group_sizes: list[int] = []

    for text in texts:
        pieces = split_for_embedding(text)
        if not pieces:
            pieces = ["空白文本"]
        flat_inputs.extend(pieces)
        group_sizes.append(len(pieces))

    embeddings = await embedding_client.embed_texts(flat_inputs)
    emb_array = np.array(embeddings, dtype=np.float32)

    repaired: list[np.ndarray] = []
    cursor = 0
    for size in group_sizes:
        part = emb_array[cursor: cursor + size]
        cursor += size
        vec = part.mean(axis=0)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        repaired.append(vec.astype(np.float32))

    return np.vstack(repaired)


def backup_file(path: Path, timestamp: str) -> Path:
    backup_path = path.parent / f"{path.name}.bak.{timestamp}"
    shutil.copy2(path, backup_path)
    return backup_path


def normalize_rows(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    mask = norms[:, 0] > 0
    vectors[mask] = vectors[mask] / norms[mask]
    return vectors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repair zero-padded embedding batches inside an existing FAISS index."
    )
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Repair target in format '书名:batch' (repeatable).",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Parse failed batch targets from a build log file.",
    )
    parser.add_argument(
        "--export-targets",
        action="store_true",
        help="Only export parsed repair targets and exit.",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=DEFAULT_INDEX_DIR,
        help=f"FAISS index directory (default: {DEFAULT_INDEX_DIR})",
    )
    parser.add_argument(
        "--books-dir",
        type=Path,
        default=TCM_BOOKS_DIR,
        help=f"TCM books directory (default: {TCM_BOOKS_DIR})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Embedding batch size used during build_index (default: 10).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only analyze and print the repair plan; do not overwrite FAISS.",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    targets: list[tuple[str, int]] = []
    for raw in args.target:
        targets.append(parse_target(raw))

    if args.log_file:
        targets.extend(parse_targets_from_log(args.log_file))

    deduped: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for item in targets:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    targets = deduped

    if not targets:
        raise SystemExit("No repair targets found. Use --target or --log-file.")

    if args.export_targets:
        for title, batch_no in targets:
            print(f"{title}:{batch_no}")
        return 0

    index_path = args.index_dir / "index.faiss"
    meta_path = args.index_dir / "metadata.pkl"
    if not index_path.exists() or not meta_path.exists():
        raise FileNotFoundError(
            f"FAISS files not found under {args.index_dir} (need index.faiss and metadata.pkl)"
        )

    index = faiss.read_index(str(index_path))
    with open(meta_path, "rb") as f:
        metadata: list[dict] = pickle.load(f)

    if index.ntotal != len(metadata):
        raise ValueError(
            f"FAISS size mismatch: index.ntotal={index.ntotal}, metadata={len(metadata)}"
        )

    logger.info("Loaded FAISS index: %s (%d vectors)", index_path, index.ntotal)

    try:
        vectors = np.array(index.reconstruct_n(0, index.ntotal), dtype=np.float32)
    except Exception as exc:
        raise RuntimeError(f"Failed to reconstruct FAISS vectors: {exc}") from exc

    rechunk_cache: dict[str, list[str]] = {}
    repair_plans: list[dict] = []

    grouped_batches: dict[str, list[int]] = defaultdict(list)
    for title, batch_no in targets:
        grouped_batches[title].append(batch_no)

    for title, batch_list in grouped_batches.items():
        try:
            seg_start, seg_end = pick_latest_segment(metadata, title)
        except Exception as exc:
            logger.warning("Skip '%s': %s", title, exc)
            continue
        seg_len = seg_end - seg_start
        logger.info(
            "Book '%s' mapped to metadata segment [%d, %d) with %d chunks",
            title,
            seg_start,
            seg_end,
            seg_len,
        )

        rechunked_texts: list[str] | None = None
        rechunk_match = False
        try:
            rechunked_texts = rechunk_cache.setdefault(title, rechunk_book(title, args.books_dir))
            rechunk_match = len(rechunked_texts) == seg_len
            logger.info(
                "Re-chunked '%s': %d chunks (%s existing FAISS segment)",
                title,
                len(rechunked_texts),
                "matches" if rechunk_match else "does not match",
            )
        except Exception as exc:
            logger.warning("Re-chunk skipped for '%s': %s", title, exc)

        for batch_no in sorted(set(batch_list)):
            batch_start = (batch_no - 1) * args.batch_size
            if batch_start >= seg_len:
                logger.warning(
                    "Skip '%s' batch %d: out of range (chunks=%d, batch_size=%d)",
                    title,
                    batch_no,
                    seg_len,
                    args.batch_size,
                )
                continue

            batch_end = min(batch_start + args.batch_size, seg_len)
            positions = list(range(seg_start + batch_start, seg_start + batch_end))
            current_texts = [metadata[pos]["chunk_text"] for pos in positions]

            if rechunk_match and rechunked_texts is not None:
                source_texts = rechunked_texts[batch_start:batch_end]
                source_mode = "rechunked"
            else:
                source_texts = current_texts
                source_mode = "stored"

            zero_like = sum(
                int(np.linalg.norm(vectors[pos]) <= 1e-8)
                for pos in positions
            )
            split_count = sum(
                1 for text in source_texts if len(text.strip()) > EMBED_INPUT_LIMIT
            )

            repair_plans.append(
                {
                    "title": title,
                    "batch_no": batch_no,
                    "positions": positions,
                    "source_texts": source_texts,
                    "source_mode": source_mode,
                    "zero_like": zero_like,
                    "split_count": split_count,
                }
            )

    if not repair_plans:
        raise ValueError("No valid repair plans were generated for the current FAISS index.")

    print("\nRepair plan:")
    for plan in repair_plans:
        pos_start = plan["positions"][0]
        pos_end = plan["positions"][-1]
        print(
            f"  - {plan['title']} batch {plan['batch_no']}: "
            f"positions {pos_start}-{pos_end}, source={plan['source_mode']}, "
            f"zero_like={plan['zero_like']}/{len(plan['positions'])}, "
            f"oversized_texts={plan['split_count']}"
        )

    if args.dry_run:
        print("\nDry run only. No FAISS files were changed.")
        return 0

    for plan in repair_plans:
        replacements = await embed_repair_texts(plan["source_texts"])
        for idx, pos in enumerate(plan["positions"]):
            vectors[pos] = replacements[idx]
        logger.info(
            "Repaired %s batch %d (%d vectors, source=%s)",
            plan["title"],
            plan["batch_no"],
            len(plan["positions"]),
            plan["source_mode"],
        )

    vectors = normalize_rows(vectors)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    index_backup = backup_file(index_path, timestamp)
    meta_backup = backup_file(meta_path, timestamp)
    logger.info("Backups created: %s, %s", index_backup, meta_backup)

    new_index = faiss.IndexFlatIP(vectors.shape[1])
    new_index.add(vectors)
    faiss.write_index(new_index, str(index_path))

    print("\nRepair completed.")
    print(f"  Index updated: {index_path}")
    print(f"  Backup index:  {index_backup}")
    print(f"  Backup meta:   {meta_backup}")
    print(f"  Repaired batches: {len(repair_plans)}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
