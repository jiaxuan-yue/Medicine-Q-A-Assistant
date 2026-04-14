#!/usr/bin/env python3
"""
Rebuild FAISS from source books listed in the build_index checkpoint.

This is the safe recovery path when checkpoint progress has advanced
but the on-disk FAISS index was not fully persisted.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.core.logger import get_logger, setup_logging
from app.integrations.vector_store import VectorStore
from build_index import (
    CHECKPOINT_PATH,
    TCM_BOOKS_DIR,
    _fmt_duration,
    _read_file_with_fallback,
    chunk_one_book,
    embed_batches_concurrent,
    load_checkpoint,
)

setup_logging("INFO")
logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild FAISS index from books listed in build_index checkpoint."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Embedding worker count (default: 3)",
    )
    parser.add_argument(
        "--save-every",
        type=int,
        default=1,
        help="Persist FAISS every N processed books (default: 1)",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=Path(settings.PROCESSED_DOCUMENTS_DIR) / "faiss_index",
        help="Target FAISS directory",
    )
    parser.add_argument(
        "--checkpoint-path",
        type=Path,
        default=CHECKPOINT_PATH,
        help="Checkpoint JSON path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be rebuilt",
    )
    return parser


def load_books_by_filenames(filenames: list[str]) -> list[dict]:
    all_files = {
        os.path.basename(path): path
        for path in sorted(glob.glob(str(TCM_BOOKS_DIR / "*.txt")))
        if not path.endswith((".downloading", ".cfg"))
    }

    books: list[dict] = []
    missing: list[str] = []
    for fname in filenames:
        fpath = all_files.get(fname)
        if not fpath:
            missing.append(fname)
            continue

        title = os.path.splitext(os.path.basename(fpath))[0]
        title = title.split("-", 1)[1] if "-" in title else title
        text = _read_file_with_fallback(fpath)
        if not text or len(text.strip()) < 50:
            logger.warning("Skip unreadable or too-short file: %s", fname)
            continue

        books.append(
            {
                "title": title,
                "text": text,
                "path": fpath,
                "filename": fname,
            }
        )

    if missing:
        logger.warning("Missing %d files from checkpoint, first few: %s", len(missing), missing[:10])
    return books


async def rebuild(args: argparse.Namespace) -> int:
    ckpt = load_checkpoint() if args.checkpoint_path == CHECKPOINT_PATH else None
    if ckpt is None:
        import json
        with open(args.checkpoint_path, "r", encoding="utf-8") as f:
            ckpt = json.load(f)

    completed_books = list(ckpt.get("completed_books", []))
    if not completed_books:
        raise ValueError(f"No completed_books found in checkpoint: {args.checkpoint_path}")

    books = load_books_by_filenames(completed_books)
    if not books:
        raise ValueError("No source books could be loaded from checkpoint filenames")

    print(f"Checkpoint books: {len(completed_books)}")
    print(f"Rebuildable books: {len(books)}")
    print(f"Target FAISS dir: {args.index_dir}")
    if args.dry_run:
        return 0

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.index_dir.exists():
        backup_dir = args.index_dir.parent / f"{args.index_dir.name}.bak.{timestamp}"
        shutil.move(str(args.index_dir), str(backup_dir))
        print(f"Backed up old FAISS dir -> {backup_dir}")

    args.index_dir.mkdir(parents=True, exist_ok=True)
    store = VectorStore()
    store._ensure_index()

    global_start = time.monotonic()
    workers = min(max(1, args.workers), 8)
    save_every = max(1, args.save_every)

    for idx, book in enumerate(books, start=1):
        elapsed = time.monotonic() - global_start
        if idx > 1:
            avg = elapsed / (idx - 1)
            remaining = len(books) - (idx - 1)
            eta = f" | ETA: ~{_fmt_duration(avg * remaining)}"
        else:
            eta = ""

        chunks = chunk_one_book(book)
        print(
            f"Rebuild {idx}/{len(books)} — {book['title']} — {len(chunks)} chunks "
            f"[Elapsed: {_fmt_duration(elapsed)}{eta}]"
        )

        if not chunks:
            logger.warning("No chunks for %s, skipped", book["title"])
            continue

        texts = [chunk["chunk_text"] for chunk in chunks]
        embeddings = await embed_batches_concurrent(texts, workers, book["title"])
        metadata = [
            {
                "chunk_id": ch["chunk_id"],
                "doc_id": ch["doc_id"],
                "doc_title": ch["doc_title"],
                "chunk_text": ch["chunk_text"],
                "metadata": ch.get("metadata", {}),
            }
            for ch in chunks
        ]
        await store.add_vectors(embeddings, metadata)
        print(f"    FAISS: +{len(embeddings)} vectors (total: {store.size})")

        if idx % save_every == 0 or idx == len(books):
            store.save(str(args.index_dir))
            print(f"    Saved checkpoint FAISS: {store.size} vectors")

    total_elapsed = time.monotonic() - global_start
    print(f"Rebuild complete in {_fmt_duration(total_elapsed)}")
    print(f"Final FAISS vectors: {store.size}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(rebuild(args))


if __name__ == "__main__":
    raise SystemExit(main())
