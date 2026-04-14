#!/usr/bin/env python3
"""
build_index.py — Standalone bootstrap script that populates Elasticsearch,
FAISS, and Neo4j with TCM ancient book content.

Features:
    - Checkpoint/resume (断点续传): survives crashes, skips already-processed books
    - Multi-threaded embedding: concurrent DashScope API batches (--workers N)
    - Progress display with ETA

Usage:
    python scripts/build_index.py --max-books 20
    python scripts/build_index.py --all
    python scripts/build_index.py --all --workers 5
    python scripts/build_index.py --all --reset
    python scripts/build_index.py --max-books 5 --skip-graph
    python scripts/build_index.py --max-books 5 --skip-embedding
    python scripts/build_index.py --status
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import re
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np

# ── Fix sys.path so `from app.xxx import xxx` works ───────────
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# ── Now import app modules ────────────────────────────────────
from app.core.config import settings
from app.core.logger import setup_logging, get_logger
from app.integrations.es_client import es_client, TCM_CHUNKS_INDEX, TCM_CHUNKS_MAPPINGS
from app.integrations.vector_store import vector_store
from app.integrations.embedding_client import embedding_client
from app.integrations.neo4j_client import neo4j_client
from app.services.chunking_service import chunking_service
from app.services.graph_build_service import (
    _extract_entities_regex,
    _RELATION_RULES,
)

setup_logging("INFO")
logger = get_logger(__name__)

# ── Paths ─────────────────────────────────────────────────────
TCM_BOOKS_DIR = Path(BACKEND_DIR).parent.parent / "TCM-Ancient-Books-master"
DICT_DIR = Path(BACKEND_DIR).parent / "data" / "dictionaries"
CHECKPOINT_PATH = Path(settings.PROCESSED_DOCUMENTS_DIR) / "build_index_checkpoint.json"

# ── Constants ─────────────────────────────────────────────────
EMBEDDING_BATCH = 10
EMBEDDING_SLEEP = 0.3  # seconds between DashScope API batches


# ═══════════════════════════════════════════════════════════════
# Checkpoint Management
# ═══════════════════════════════════════════════════════════════

def _default_checkpoint() -> dict:
    return {
        "completed_books": [],
        "last_updated": None,
        "stats": {
            "total_chunks": 0,
            "total_vectors": 0,
            "total_es_docs": 0,
            "total_entities": 0,
            "total_relations": 0,
        },
    }


def load_checkpoint() -> dict:
    """Load checkpoint from disk, or return empty checkpoint."""
    if CHECKPOINT_PATH.exists():
        try:
            with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as exc:
            print(f"  ⚠ Could not read checkpoint: {exc}, starting fresh")
    return _default_checkpoint()


def save_checkpoint(ckpt: dict) -> None:
    """Atomically save checkpoint (write tmp then rename)."""
    ckpt["last_updated"] = datetime.now().isoformat(timespec="seconds")
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(CHECKPOINT_PATH.parent), suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(ckpt, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, str(CHECKPOINT_PATH))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def clear_checkpoint() -> None:
    """Remove checkpoint file."""
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()
        print(f"  ✓ Checkpoint cleared: {CHECKPOINT_PATH}")


def show_status() -> None:
    """Print current checkpoint status and exit."""
    # Count total available books
    pattern = str(TCM_BOOKS_DIR / "*.txt")
    all_files = sorted(glob.glob(pattern))
    all_files = [f for f in all_files if not f.endswith((".downloading", ".cfg"))]
    total_available = len(all_files)

    print(f"Checkpoint: {CHECKPOINT_PATH}")
    if not CHECKPOINT_PATH.exists():
        print("  No checkpoint found — no books processed yet.")
        print(f"  Total books available: {total_available}")
        return

    ckpt = load_checkpoint()
    done = len(ckpt.get("completed_books", []))
    stats = ckpt.get("stats", {})
    last = ckpt.get("last_updated", "N/A")

    print(f"Books processed: {done}/{total_available}")
    print(
        f"Chunks: {stats.get('total_chunks', 0)} | "
        f"Vectors: {stats.get('total_vectors', 0)} | "
        f"ES docs: {stats.get('total_es_docs', 0)}"
    )
    print(
        f"Entities: {stats.get('total_entities', 0)} | "
        f"Relations: {stats.get('total_relations', 0)}"
    )
    print(f"Last updated: {last}")


# ═══════════════════════════════════════════════════════════════
# Progress / Timer Helpers
# ═══════════════════════════════════════════════════════════════

def _fmt_duration(seconds: float) -> str:
    """Format seconds as 'Xh Ym Zs' or 'Ym Zs'."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s"


# ═══════════════════════════════════════════════════════════════
# Step 1: Load TCM Book Files
# ═══════════════════════════════════════════════════════════════

def load_books(books_dir: Path, max_books: int | None = None) -> list[dict]:
    """Read .txt files, returning list of {title, text, path, filename}."""
    pattern = str(books_dir / "*.txt")
    files = sorted(glob.glob(pattern))
    # Skip downloading/temp files
    files = [f for f in files if not f.endswith((".downloading", ".cfg"))]

    if max_books is not None:
        files = files[:max_books]

    books: list[dict] = []
    for idx, fpath in enumerate(files):
        fname = os.path.basename(fpath)
        title = os.path.splitext(fname)[0]
        # Strip leading number prefix like "000-"
        title = re.sub(r"^\d+-", "", title)

        text = _read_file_with_fallback(fpath)
        if not text or len(text.strip()) < 50:
            print(f"  ⚠ Skipping {fname} (empty or too short)")
            continue

        books.append({
            "title": title,
            "text": text,
            "path": fpath,
            "filename": fname,
        })

    print(f"\n✓ Found {len(books)} books to consider\n")
    return books


def _read_file_with_fallback(fpath: str) -> str:
    """Try multiple encodings to read a text file."""
    for enc in ("utf-8", "gb18030", "gbk", "iso-8859-1"):
        try:
            with open(fpath, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""


# ═══════════════════════════════════════════════════════════════
# Step 2: Chunk a Single Book
# ═══════════════════════════════════════════════════════════════

def chunk_one_book(book: dict) -> list[dict]:
    """Chunk one book, returning list of chunk dicts."""
    # Keep document/chunk ids stable across retries so ES upserts overwrite
    # previous partial attempts instead of creating duplicate documents.
    stable_source = book.get("filename") or book.get("path") or book["title"]
    doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, stable_source))
    raw_chunks = chunking_service.chunk_text(book["text"], chunk_size=512, overlap=50)
    chunks: list[dict] = []
    for ch in raw_chunks:
        chunk_id = f"{doc_id}-{ch['chunk_index']}"
        chunks.append({
            "doc_id": doc_id,
            "doc_title": book["title"],
            "chunk_id": chunk_id,
            "chunk_text": ch["chunk_text"],
            "metadata": ch.get("metadata_json", {}),
        })
    return chunks


# ═══════════════════════════════════════════════════════════════
# Step 3: Index into Elasticsearch
# ═══════════════════════════════════════════════════════════════

# Fallback mapping without IK analyzer (when IK plugin not installed)
TCM_CHUNKS_MAPPINGS_FALLBACK = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            "chunk_text": {"type": "text"},
            "doc_id": {"type": "keyword"},
            "chunk_id": {"type": "keyword"},
            "doc_title": {"type": "keyword"},
            "metadata": {"type": "object", "enabled": False},
        }
    },
}


async def _ensure_index_with_fallback() -> None:
    """Try IK analyzer mapping first; fall back to standard if IK not installed."""
    try:
        exists = await es_client._client.indices.exists(index=TCM_CHUNKS_INDEX)
        if exists:
            print(f"  Index '{TCM_CHUNKS_INDEX}' already exists")
            return
    except Exception:
        pass

    # Try with IK analyzer first
    try:
        await es_client._client.indices.create(
            index=TCM_CHUNKS_INDEX,
            settings=TCM_CHUNKS_MAPPINGS.get("settings"),
            mappings=TCM_CHUNKS_MAPPINGS.get("mappings"),
        )
        print(f"  Created index '{TCM_CHUNKS_INDEX}' with IK analyzer")
        return
    except Exception as exc:
        if "ik_max_word" in str(exc):
            print("  IK analyzer not available, using standard analyzer fallback")
        else:
            print(f"  Index creation failed: {exc}, trying fallback...")

    # Fallback without IK
    try:
        await es_client._client.indices.create(
            index=TCM_CHUNKS_INDEX,
            settings=TCM_CHUNKS_MAPPINGS_FALLBACK.get("settings"),
            mappings=TCM_CHUNKS_MAPPINGS_FALLBACK.get("mappings"),
        )
        print(f"  Created index '{TCM_CHUNKS_INDEX}' with standard analyzer (fallback)")
    except Exception as exc2:
        print(f"  ✗ Could not create index: {exc2}")


async def index_es_chunks(chunks: list[dict]) -> int:
    """Bulk-index chunks for one book into ES."""
    if not es_client.available:
        return 0

    BATCH = 500
    total_indexed = 0
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i : i + BATCH]
        n = await es_client.bulk_index(TCM_CHUNKS_INDEX, batch)
        total_indexed += n
    return total_indexed


# ═══════════════════════════════════════════════════════════════
# Step 4: Concurrent Embedding + FAISS
# ═══════════════════════════════════════════════════════════════

def _embed_single_batch_sync(batch: list[str]) -> list[list[float]]:
    """Synchronous single-batch DashScope call (up to 10 texts)."""
    from dashscope import TextEmbedding
    response = TextEmbedding.call(
        model=settings.EMBEDDING_MODEL,
        input=batch,
        dimension=settings.EMBEDDING_DIM,
    )
    if response.status_code == 200:
        return [item["embedding"] for item in response.output["embeddings"]]
    raise Exception(f"Embedding API error: {response.code} - {response.message}")


async def embed_batches_concurrent(
    texts: list[str],
    workers: int,
    book_label: str = "",
    *,
    batch_retries: int = 3,
    zero_pad_on_failure: bool = False,
) -> list[list[float]]:
    """Embed texts in concurrent batches using a thread pool.

    Args:
        texts: All texts to embed for one book.
        workers: Number of concurrent workers.
        book_label: For progress display.

    Returns:
        List of embedding vectors, same order as texts.
    """
    # Split into batches of EMBEDDING_BATCH
    batches: list[list[str]] = []
    for i in range(0, len(texts), EMBEDDING_BATCH):
        batches.append(texts[i : i + EMBEDDING_BATCH])

    total_batches = len(batches)
    results: list[list[list[float]] | None] = [None] * total_batches
    completed = 0
    lock = asyncio.Lock()

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=workers)
    semaphore = asyncio.Semaphore(workers)

    async def embed_one(batch_idx: int, batch: list[str]) -> None:
        nonlocal completed
        async with semaphore:
            last_error: Exception | None = None
            for attempt in range(1, batch_retries + 1):
                try:
                    vectors = await loop.run_in_executor(
                        executor, _embed_single_batch_sync, batch
                    )
                    results[batch_idx] = vectors
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < batch_retries:
                        backoff = min(2 * attempt, 10)
                        logger.warning(
                            "Batch %d failed (attempt %d/%d): %s, retrying in %ss...",
                            batch_idx + 1,
                            attempt,
                            batch_retries,
                            exc,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue

                    if zero_pad_on_failure:
                        logger.warning(
                            "Batch %d failed after %d attempts: %s, zero-padding",
                            batch_idx + 1,
                            batch_retries,
                            exc,
                        )
                        results[batch_idx] = [
                            [0.0] * settings.EMBEDDING_DIM
                        ] * len(batch)
                        break

                    raise RuntimeError(
                        f"Batch {batch_idx + 1} failed after "
                        f"{batch_retries} attempts: {last_error}"
                    ) from last_error

            async with lock:
                completed += 1
                if completed % max(1, total_batches // 10) == 0 or completed == total_batches:
                    print(
                        f"    Embedding: batch {completed}/{total_batches} "
                        f"(workers={workers})"
                    )

            # Small sleep for rate limiting
            await asyncio.sleep(EMBEDDING_SLEEP)

    tasks = [embed_one(i, b) for i, b in enumerate(batches)]
    await asyncio.gather(*tasks)
    executor.shutdown(wait=False)

    # Flatten results in order
    all_embeddings: list[list[float]] = []
    for r in results:
        if r is not None:
            all_embeddings.extend(r)
        else:
            # Should not happen, but safety fallback
            all_embeddings.extend([[0.0] * settings.EMBEDDING_DIM] * EMBEDDING_BATCH)

    return all_embeddings


async def embed_and_store_chunks(
    chunks: list[dict],
    workers: int,
    book_title: str,
    *,
    batch_retries: int = 3,
) -> int:
    """Embed chunks for one book and add to FAISS index."""
    texts = [ch["chunk_text"] for ch in chunks]
    embeddings = await embed_batches_concurrent(
        texts,
        workers,
        book_title,
        batch_retries=batch_retries,
        zero_pad_on_failure=False,
    )

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

    await vector_store.add_vectors(embeddings, metadata)
    return len(embeddings)


# ═══════════════════════════════════════════════════════════════
# Step 5: Build Knowledge Graph in Neo4j
# ═══════════════════════════════════════════════════════════════

def _load_dict_names(json_path: Path) -> set[str]:
    """Load entity names (keys) from a dictionary JSON file."""
    if not json_path.exists():
        return set()
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    names = set(data.keys())
    # Also add aliases
    for aliases in data.values():
        if isinstance(aliases, list):
            names.update(aliases)
    return names


def _build_dict_regex(names: set[str]) -> re.Pattern | None:
    """Build a regex pattern from a set of names, longest-first."""
    if not names:
        return None
    sorted_names = sorted(names, key=len, reverse=True)
    escaped = [re.escape(n) for n in sorted_names]
    return re.compile("|".join(escaped))


# Module-level caches for dict regexes (loaded once)
_dict_regex_map: list[tuple[re.Pattern | None, str]] | None = None
_graph_entity_set: set[tuple[str, str]] = set()


def _ensure_dict_regexes() -> list[tuple[re.Pattern | None, str]]:
    global _dict_regex_map
    if _dict_regex_map is not None:
        return _dict_regex_map
    herb_names = _load_dict_names(DICT_DIR / "herb_aliases.json")
    symptom_names = _load_dict_names(DICT_DIR / "symptom_synonyms.json")
    formula_names = _load_dict_names(DICT_DIR / "formula_aliases.json")
    _dict_regex_map = [
        (_build_dict_regex(herb_names), "Herb"),
        (_build_dict_regex(symptom_names), "Symptom"),
        (_build_dict_regex(formula_names), "Formula"),
    ]
    return _dict_regex_map


async def build_graph_for_book(chunks: list[dict]) -> tuple[int, int]:
    """Extract entities from sampled chunks and create Neo4j nodes & rels."""
    if not neo4j_client.available:
        return 0, 0

    global _graph_entity_set
    dict_regex_map = _ensure_dict_regexes()

    total_entities = 0
    total_relations = 0

    # Sample chunks for this book (at most ~50 per book for speed)
    step = max(1, len(chunks) // 50)
    sampled = chunks[::step]

    for chunk in sampled:
        text = chunk["chunk_text"]
        if not text:
            continue

        entities = _extract_entities_regex(text)
        seen_names = {e["name"] for e in entities}
        for pattern, etype in dict_regex_map:
            if pattern is None:
                continue
            for m in pattern.finditer(text):
                name = m.group(0)
                if name not in seen_names and len(name) >= 2:
                    seen_names.add(name)
                    entities.append({"name": name, "type": etype})

        if not entities:
            continue

        for ent in entities:
            key = (ent["name"], ent["type"])
            if key not in _graph_entity_set:
                _graph_entity_set.add(key)
                await neo4j_client.create_entity(
                    name=ent["name"],
                    entity_type=ent["type"],
                    properties={"source_doc": chunk.get("doc_title", "")},
                )
                total_entities += 1

        entity_list = [(e["name"], e["type"]) for e in entities]
        for i, (name_a, type_a) in enumerate(entity_list):
            for j, (name_b, type_b) in enumerate(entity_list):
                if i >= j:
                    continue
                rel = _RELATION_RULES.get((type_a, type_b))
                if rel:
                    await neo4j_client.create_relationship(
                        from_name=name_a, to_name=name_b, rel_type=rel,
                        properties={"source_doc": chunk.get("doc_title", "")},
                    )
                    total_relations += 1
                rel_rev = _RELATION_RULES.get((type_b, type_a))
                if rel_rev:
                    await neo4j_client.create_relationship(
                        from_name=name_b, to_name=name_a, rel_type=rel_rev,
                        properties={"source_doc": chunk.get("doc_title", "")},
                    )
                    total_relations += 1

    return total_entities, total_relations


# ═══════════════════════════════════════════════════════════════
# Verification
# ═══════════════════════════════════════════════════════════════

async def verify() -> None:
    """Print verification summary for all three backends."""
    print("=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    # ES
    if es_client.available:
        try:
            resp = await es_client._client.count(index=TCM_CHUNKS_INDEX)
            print(f"  Elasticsearch: {resp['count']} documents in '{TCM_CHUNKS_INDEX}'")
        except Exception as exc:
            print(f"  Elasticsearch: error counting — {exc}")
    else:
        print("  Elasticsearch: not available")

    # FAISS
    print(f"  FAISS: {vector_store.size} vectors (available={vector_store.available})")

    # Neo4j
    if neo4j_client.available:
        nodes = await neo4j_client.run_query("MATCH (n) RETURN count(n) AS cnt")
        rels = await neo4j_client.run_query("MATCH ()-[r]->() RETURN count(r) AS cnt")
        n_count = nodes[0]["cnt"] if nodes else 0
        r_count = rels[0]["cnt"] if rels else 0
        print(f"  Neo4j: {n_count} nodes, {r_count} relationships")
    else:
        print("  Neo4j: not available")

    print("=" * 60)


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

async def main(args: argparse.Namespace) -> None:
    # ── Handle --status ───────────────────────────────────────
    if args.status:
        show_status()
        return

    # ── Handle --reset ────────────────────────────────────────
    if args.reset:
        clear_checkpoint()

    max_books = None if args.all else args.max_books
    workers = min(args.workers, 8)
    save_every = max(1, args.save_every)
    book_retries = max(1, args.book_retries)

    print("=" * 60)
    print("TCM-RAG Bootstrap Index Builder")
    print(f"  Books dir:       {TCM_BOOKS_DIR}")
    print(f"  Max books:       {'ALL' if max_books is None else max_books}")
    print(f"  Workers:         {workers}")
    print(f"  Book retries:    {book_retries}")
    print(f"  Skip embedding:  {args.skip_embedding}")
    print(f"  Skip graph:      {args.skip_graph}")
    print(f"  Save every:      {save_every} book(s)")
    print(f"  Checkpoint:      {CHECKPOINT_PATH}")
    print("=" * 60)

    # ── Load checkpoint ───────────────────────────────────────
    ckpt = load_checkpoint()
    completed_set = set(ckpt.get("completed_books", []))
    if completed_set:
        print(
            f"\n📌 Resuming from checkpoint: {len(completed_set)} books already processed"
        )
    initial_completed_count = len(completed_set)

    # ── Step 1: Load books ────────────────────────────────────
    print("\nStep 1: Loading TCM book files...")
    books = load_books(TCM_BOOKS_DIR, max_books=max_books)
    if not books:
        print("No books found — exiting.")
        return

    total_books = len(books)
    # Filter to only unprocessed books
    pending_books = [b for b in books if b["filename"] not in completed_set]
    if not pending_books:
        print("All books already processed! Use --reset to start fresh.")
        await verify()
        return

    print(
        f"  {len(pending_books)} books to process "
        f"({len(completed_set)} already done, {total_books} total)\n"
    )

    # ── Initialize services ───────────────────────────────────
    print("Initializing services...")
    await es_client.init()
    if es_client.available:
        await _ensure_index_with_fallback()

    # Load existing FAISS index for incremental adds
    if not args.skip_embedding:
        faiss_dir = os.path.join(settings.PROCESSED_DOCUMENTS_DIR, "faiss_index")
        if os.path.exists(os.path.join(faiss_dir, "index.faiss")) and completed_set:
            vector_store.load(faiss_dir)
            print(f"  Loaded existing FAISS index: {vector_store.size} vectors")
        else:
            vector_store._ensure_index()
            print("  Initialized fresh FAISS index")

    if not args.skip_graph:
        await neo4j_client.init()

    # ── Process books one by one ──────────────────────────────
    global_start = time.monotonic()
    fatal_exc: Exception | None = None

    for book_idx, book in enumerate(pending_books):
        book_start = time.monotonic()
        elapsed_total = book_start - global_start
        books_done_so_far = book_idx  # within this run
        overall_done = initial_completed_count + book_idx

        # ETA calculation
        if books_done_so_far > 0:
            avg_per_book = elapsed_total / books_done_so_far
            remaining = len(pending_books) - books_done_so_far
            eta_str = f" | ETA: ~{_fmt_duration(avg_per_book * remaining)}"
        else:
            eta_str = ""

        pct = (overall_done + 1) / total_books * 100

        book_succeeded = False

        for attempt in range(1, book_retries + 1):
            faiss_appended = False
            chunks: list[dict] = []
            es_count = 0
            vec_count = 0
            ent_count = 0
            rel_count = 0

            try:
                # ── 2. Chunk ──────────────────────────────────
                chunks = chunk_one_book(book)
                attempt_suffix = f" [attempt {attempt}/{book_retries}]" if book_retries > 1 else ""
                print(
                    f"\nBook {overall_done + 1}/{total_books} ({pct:.1f}%) — "
                    f"{book['title']} — {len(chunks)} chunks{attempt_suffix}"
                    f"  [Elapsed: {_fmt_duration(elapsed_total)}{eta_str}]"
                )

                if not chunks:
                    print("  ⚠ No chunks, skipping")
                    ckpt["completed_books"].append(book["filename"])
                    completed_set.add(book["filename"])
                    save_checkpoint(ckpt)
                    book_succeeded = True
                    break

                # ── 3. Elasticsearch ──────────────────────────
                es_count = await index_es_chunks(chunks)
                if es_count:
                    print(f"    ES: indexed {es_count} chunks")

                # ── 4. Embeddings + FAISS ─────────────────────
                if not args.skip_embedding:
                    vec_count = await embed_and_store_chunks(
                        chunks,
                        workers,
                        book["title"],
                        batch_retries=args.batch_retries,
                    )
                    faiss_appended = vec_count > 0
                    print(f"    FAISS: +{vec_count} vectors (total: {vector_store.size})")
                else:
                    print("    Embedding: skipped (--skip-embedding)")

                # ── 5. Knowledge graph ────────────────────────
                if not args.skip_graph:
                    ent_count, rel_count = await build_graph_for_book(chunks)
                    if ent_count or rel_count:
                        print(f"    Graph: +{ent_count} entities, +{rel_count} relations")
                else:
                    print("    Graph: skipped (--skip-graph)")

                # ── Save checkpoint ───────────────────────────
                ckpt["completed_books"].append(book["filename"])
                completed_set.add(book["filename"])
                ckpt["stats"]["total_chunks"] += len(chunks)
                ckpt["stats"]["total_vectors"] += vec_count
                ckpt["stats"]["total_es_docs"] += es_count
                ckpt["stats"]["total_entities"] += ent_count
                ckpt["stats"]["total_relations"] += rel_count
                save_checkpoint(ckpt)

                if (
                    not args.skip_embedding
                    and vector_store.available
                    and ((book_idx + 1) % save_every == 0 or (book_idx + 1) == len(pending_books))
                ):
                    faiss_dir = os.path.join(settings.PROCESSED_DOCUMENTS_DIR, "faiss_index")
                    os.makedirs(faiss_dir, exist_ok=True)
                    vector_store.save(faiss_dir)
                    print(f"    FAISS checkpoint saved: {vector_store.size} vectors")

                book_succeeded = True
                break

            except Exception as exc:
                logger.exception("Book '%s' attempt %d failed", book["title"], attempt)

                if faiss_appended:
                    if not args.skip_embedding and vector_store.available:
                        faiss_dir = os.path.join(settings.PROCESSED_DOCUMENTS_DIR, "faiss_index")
                        os.makedirs(faiss_dir, exist_ok=True)
                        vector_store.save(faiss_dir)
                    fatal_exc = RuntimeError(
                        f"Book '{book['title']}' failed after FAISS append; "
                        "stopped to avoid duplicate vectors. Rerun will resume from this book."
                    )
                    print(f"  ✗ {fatal_exc}")
                    break

                if attempt < book_retries:
                    backoff = min(5 * attempt, 30)
                    print(
                        f"  ⚠ Book failed: {exc}\n"
                        f"    retrying in {backoff}s "
                        f"({attempt}/{book_retries})..."
                    )
                    await asyncio.sleep(backoff)
                    continue

                if not args.skip_embedding and vector_store.available:
                    faiss_dir = os.path.join(settings.PROCESSED_DOCUMENTS_DIR, "faiss_index")
                    os.makedirs(faiss_dir, exist_ok=True)
                    vector_store.save(faiss_dir)
                fatal_exc = RuntimeError(
                    f"Book '{book['title']}' failed after {book_retries} attempts. "
                    "Progress before this book has been saved; rerun will resume here."
                )
                print(f"  ✗ {fatal_exc}")
                break

        if fatal_exc is not None:
            break
        if not book_succeeded:
            break

    # ── Save FAISS to disk ────────────────────────────────────
    if not args.skip_embedding and vector_store.available:
        faiss_dir = os.path.join(settings.PROCESSED_DOCUMENTS_DIR, "faiss_index")
        os.makedirs(faiss_dir, exist_ok=True)
        vector_store.save(faiss_dir)
        print(f"\n✓ Saved FAISS index: {vector_store.size} vectors")

    # ── Verify ────────────────────────────────────────────────
    await verify()

    # ── Cleanup ───────────────────────────────────────────────
    await es_client.close()
    await neo4j_client.close()

    total_time = time.monotonic() - global_start
    print(f"\n✅ Bootstrap complete! Processed {len(pending_books)} books in {_fmt_duration(total_time)}")
    print(f"   Total books in checkpoint: {len(ckpt['completed_books'])}/{total_books}")
    if fatal_exc is not None:
        raise fatal_exc


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TCM-RAG Bootstrap Index Builder")
    parser.add_argument(
        "--max-books", type=int, default=20,
        help="Number of books to index (default: 20)",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Index all books (overrides --max-books)",
    )
    parser.add_argument(
        "--skip-graph", action="store_true",
        help="Skip Neo4j knowledge graph construction",
    )
    parser.add_argument(
        "--skip-embedding", action="store_true",
        help="Skip FAISS embedding generation",
    )
    parser.add_argument(
        "--workers", type=int, default=3,
        help="Number of concurrent embedding workers (default: 3, max: 8)",
    )
    parser.add_argument(
        "--save-every", type=int, default=1,
        help="Persist FAISS to disk every N processed books (default: 1)",
    )
    parser.add_argument(
        "--book-retries", type=int, default=3,
        help="Retry each failed book up to N times before stopping (default: 3)",
    )
    parser.add_argument(
        "--batch-retries", type=int, default=4,
        help="Retry each failed embedding batch up to N times before failing the book (default: 4)",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Clear checkpoint and start fresh",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show current checkpoint status without processing",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = cli()
    asyncio.run(main(args))
