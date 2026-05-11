#!/usr/bin/env python3
"""Run a deterministic local retrieval regression against FAISS metadata.

This script is dependency-light on purpose:
- no HTTP server required
- no external embedding / ES service required
- reads only the persisted FAISS metadata snapshot

It is useful for quickly validating book/entity lookup regressions.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.services.local_recall_utils import extract_heading_entity, rank_metadata_chunks

DEFAULT_METADATA = PROJECT_ROOT / "data" / "processed" / "faiss_index" / "metadata.pkl"
DEFAULT_SUMMARY = PROJECT_ROOT / "data" / "eval" / "local_retrieval_regression_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地召回回归测试（书名/实体精确召回）")
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--limit", type=int, default=120, help="最多采样多少个唯一书名+实体 case")
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
                "chunk_id": item.get("chunk_id", ""),
                "queries": [
                    f"{entity}这种草药有什么功效？",
                    f"《{doc_title}》中提到的{entity}有什么功效？",
                ],
            }
        )
        if len(cases) >= limit:
            break
    return cases


def naive_rank(metadata: list[dict], *, query: str, top_k: int = 10) -> list[dict]:
    query = query.strip()
    ranked: list[dict] = []
    for item in metadata:
        text = str(item.get("chunk_text") or "")
        doc_title = str(item.get("doc_title") or "")
        score = 0.0
        if query and query in text:
            score += 10.0
        if query and query in doc_title:
            score += 4.0
        if score <= 0:
            continue
        candidate = dict(item)
        candidate["score"] = score
        ranked.append(candidate)
    ranked.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return ranked[:top_k]


def measure(metadata: list[dict], cases: list[dict]) -> dict:
    total_queries = 0
    baseline_hits = {1: 0, 3: 0, 10: 0}
    tuned_hits = {1: 0, 3: 0, 10: 0}
    examples: list[dict] = []

    for case in cases:
        for query in case["queries"]:
            total_queries += 1
            baseline = naive_rank(metadata, query=query, top_k=10)
            tuned = rank_metadata_chunks(
                metadata,
                query_terms=[query, case["entity"], case["doc_title"]],
                entities=[case["entity"]],
                book_name=case["doc_title"],
                top_k=10,
            )

            for k in baseline_hits:
                if any(item.get("chunk_id") == case["chunk_id"] for item in baseline[:k]):
                    baseline_hits[k] += 1
                if any(item.get("chunk_id") == case["chunk_id"] for item in tuned[:k]):
                    tuned_hits[k] += 1

            if len(examples) < 8:
                examples.append(
                    {
                        "query": query,
                        "target_doc": case["doc_title"],
                        "target_entity": case["entity"],
                        "baseline_top1": {
                            "doc_title": baseline[0].get("doc_title", "") if baseline else "",
                            "heading": extract_heading_entity(baseline[0].get("chunk_text", "")) if baseline else "",
                        },
                        "tuned_top1": {
                            "doc_title": tuned[0].get("doc_title", "") if tuned else "",
                            "heading": extract_heading_entity(tuned[0].get("chunk_text", "")) if tuned else "",
                        },
                    }
                )

    summary = {
        "metadata_items": len(metadata),
        "cases": len(cases),
        "queries": total_queries,
        "baseline_recall_at_1": round(baseline_hits[1] / total_queries, 4) if total_queries else 0.0,
        "baseline_recall_at_3": round(baseline_hits[3] / total_queries, 4) if total_queries else 0.0,
        "baseline_recall_at_10": round(baseline_hits[10] / total_queries, 4) if total_queries else 0.0,
        "tuned_recall_at_1": round(tuned_hits[1] / total_queries, 4) if total_queries else 0.0,
        "tuned_recall_at_3": round(tuned_hits[3] / total_queries, 4) if total_queries else 0.0,
        "tuned_recall_at_10": round(tuned_hits[10] / total_queries, 4) if total_queries else 0.0,
        "examples": examples,
    }
    return summary


def main() -> None:
    args = parse_args()
    metadata = load_metadata(Path(args.metadata))
    cases = build_cases(metadata, args.limit)
    summary = measure(metadata, cases)

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
