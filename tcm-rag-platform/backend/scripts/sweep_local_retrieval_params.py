#!/usr/bin/env python3
"""Parameter sweep for local retrieval fusion.

This script stays dependency-light so it can run in the current workspace
without Elasticsearch, DashScope, or the full backend runtime.

It evaluates a proxy hybrid retrieval setup over persisted FAISS metadata:
- sparse_proxy: looser lexical matching without hard book filtering
- lexical: strict book/entity-aware recall based on heading/entity heuristics
- fusion: Reciprocal Rank Fusion over the two channels
"""

from __future__ import annotations

import argparse
import itertools
import json
import pickle
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.services.local_recall_utils import (
    extract_heading_entity,
    filter_entity_candidates,
    rank_metadata_chunks,
)

DEFAULT_METADATA = PROJECT_ROOT / "data" / "processed" / "faiss_index" / "metadata.pkl"
DEFAULT_SUMMARY = PROJECT_ROOT / "data" / "eval" / "local_retrieval_param_sweep_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地召回参数 sweep（无需外部服务）")
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--limit", type=int, default=120, help="最多采样多少个唯一书名+实体 case")
    parser.add_argument("--top-n", type=int, default=12, help="输出前多少组参数")
    return parser.parse_args()


def load_metadata(path: Path) -> list[dict]:
    with path.open("rb") as f:
        return pickle.load(f)


def build_cases(metadata: list[dict], limit: int) -> list[dict]:
    cases: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in metadata:
        doc_title = str(item.get("doc_title") or "")
        chunk_text = str(item.get("chunk_text") or "")
        entity = extract_heading_entity(chunk_text)
        if not doc_title or not entity:
            continue
        if len(entity) < 2 or len(entity) > 8:
            continue
        if "味" not in chunk_text and "主" not in chunk_text:
            continue
        key = (doc_title, entity)
        if key in seen:
            continue
        seen.add(key)
        cases.append(
            {
                "doc_title": doc_title,
                "entity": entity,
                "chunk_id": str(item.get("chunk_id") or ""),
                "queries": [
                    f"{entity}这种草药有什么功效？",
                    f"《{doc_title}》中提到的{entity}有什么功效？",
                ],
            }
        )
        if len(cases) >= limit:
            break
    return cases


def proxy_sparse_rank(
    metadata: list[dict],
    *,
    query: str,
    entity: str,
    doc_title: str,
    top_k: int,
) -> list[dict]:
    """A loose sparse-like ranking signal over local metadata.

    This intentionally does not hard-filter to a book. It is meant to emulate
    the noisier behavior of BM25 before the new exact lexical channel reranks
    the result set.
    """
    query_terms = filter_entity_candidates([entity, doc_title, query])
    ranked: list[dict] = []
    for item in metadata:
        text = str(item.get("chunk_text") or "")
        title = str(item.get("doc_title") or "")
        heading = extract_heading_entity(text)
        score = 0.0

        if title == doc_title:
            score += 3.0
        elif doc_title and doc_title in title:
            score += 1.0

        if heading == entity:
            score += 9.0
        elif entity and entity in text:
            score += 5.0

        for term in query_terms:
            if term == entity or term == doc_title:
                continue
            if term in text:
                score += 1.5
            elif term in title:
                score += 0.5

        if score <= 0:
            continue

        candidate = dict(item)
        candidate["score"] = round(score, 4)
        ranked.append(candidate)

    ranked.sort(
        key=lambda item: (
            float(item.get("score", 0.0)),
            extract_heading_entity(str(item.get("chunk_text") or "")) == entity,
        ),
        reverse=True,
    )
    return ranked[:top_k]


def rrf_fuse(channels: list[list[dict]], *, rrf_k: int, top_k: int) -> list[dict]:
    scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}
    for channel_docs in channels:
        for rank, item in enumerate(channel_docs):
            chunk_id = str(item.get("chunk_id") or "")
            if not chunk_id:
                continue
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank + 1)
            doc_map.setdefault(chunk_id, item)

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return [doc_map[chunk_id] for chunk_id, _ in ranked]


def reciprocal_rank(items: list[dict], target_chunk_id: str) -> float:
    for idx, item in enumerate(items, start=1):
        if item.get("chunk_id") == target_chunk_id:
            return 1.0 / idx
    return 0.0


def precompute_candidates(metadata: list[dict], cases: list[dict], max_sparse_top_k: int, max_lexical_top_k: int) -> list[dict]:
    prepared: list[dict] = []
    for case in cases:
        for query in case["queries"]:
            sparse = proxy_sparse_rank(
                metadata,
                query=query,
                entity=case["entity"],
                doc_title=case["doc_title"],
                top_k=max_sparse_top_k,
            )
            lexical = rank_metadata_chunks(
                metadata,
                query_terms=[query, case["entity"], case["doc_title"]],
                entities=[case["entity"]],
                book_name=case["doc_title"],
                top_k=max_lexical_top_k,
            )
            prepared.append(
                {
                    "query": query,
                    "target_doc": case["doc_title"],
                    "target_entity": case["entity"],
                    "target_chunk_id": case["chunk_id"],
                    "sparse": sparse,
                    "lexical": lexical,
                }
            )
    return prepared


def evaluate_combo(prepared: list[dict], *, sparse_top_k: int, lexical_top_k: int, fusion_top_k: int, rrf_k: int) -> dict:
    total = len(prepared)
    hits = {1: 0, 3: 0, 10: 0}
    mrr = 0.0
    sample_hits: list[dict] = []

    for item in prepared:
        fused = rrf_fuse(
            [
                item["sparse"][:sparse_top_k],
                item["lexical"][:lexical_top_k],
            ],
            rrf_k=rrf_k,
            top_k=max(10, fusion_top_k),
        )

        rr = reciprocal_rank(fused[:10], item["target_chunk_id"])
        mrr += rr
        for k in hits:
            if any(candidate.get("chunk_id") == item["target_chunk_id"] for candidate in fused[:k]):
                hits[k] += 1

        if rr > 0 and len(sample_hits) < 5:
            top1 = fused[0] if fused else {}
            sample_hits.append(
                {
                    "query": item["query"],
                    "target_doc": item["target_doc"],
                    "target_entity": item["target_entity"],
                    "top1_doc": top1.get("doc_title", ""),
                    "top1_heading": extract_heading_entity(str(top1.get("chunk_text") or "")),
                }
            )

    return {
        "SPARSE_TOP_K": sparse_top_k,
        "LEXICAL_TOP_K": lexical_top_k,
        "FUSION_TOP_K": fusion_top_k,
        "RRF_K": rrf_k,
        "queries": total,
        "recall_at_1": round(hits[1] / total, 4) if total else 0.0,
        "recall_at_3": round(hits[3] / total, 4) if total else 0.0,
        "recall_at_10": round(hits[10] / total, 4) if total else 0.0,
        "mrr_at_10": round(mrr / total, 4) if total else 0.0,
        "sample_hits": sample_hits,
    }


def main() -> None:
    args = parse_args()
    metadata = load_metadata(Path(args.metadata))
    cases = build_cases(metadata, args.limit)

    sparse_candidates = [8, 12, 20, 30]
    lexical_candidates = [3, 5, 8, 12]
    fusion_candidates = [3, 5, 8, 12]
    rrf_candidates = [10, 30, 60]

    prepared = precompute_candidates(
        metadata,
        cases,
        max_sparse_top_k=max(sparse_candidates),
        max_lexical_top_k=max(lexical_candidates),
    )

    results = [
        evaluate_combo(
            prepared,
            sparse_top_k=sparse_top_k,
            lexical_top_k=lexical_top_k,
            fusion_top_k=fusion_top_k,
            rrf_k=rrf_k,
        )
        for sparse_top_k, lexical_top_k, fusion_top_k, rrf_k in itertools.product(
            sparse_candidates,
            lexical_candidates,
            fusion_candidates,
            rrf_candidates,
        )
    ]

    results.sort(
        key=lambda row: (
            row["recall_at_1"],
            row["mrr_at_10"],
            row["recall_at_3"],
            -row["RRF_K"],
        ),
        reverse=True,
    )

    summary = {
        "metadata_items": len(metadata),
        "cases": len(cases),
        "queries": len(prepared),
        "sweep_space": {
            "SPARSE_TOP_K": sparse_candidates,
            "LEXICAL_TOP_K": lexical_candidates,
            "FUSION_TOP_K": fusion_candidates,
            "RRF_K": rrf_candidates,
        },
        "best": results[0] if results else {},
        "top_results": results[: args.top_n],
    }

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
