#!/usr/bin/env python3
"""Backfill weak-supervision metrics for existing scope50 eval results."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = PROJECT_ROOT / "data" / "eval" / "scope50_eval_300.jsonl"
DEFAULT_RESULTS = PROJECT_ROOT / "data" / "eval" / "scope50_eval_results.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "eval" / "scope50_eval_results_weak.jsonl"
DEFAULT_SUMMARY = PROJECT_ROOT / "data" / "eval" / "scope50_eval_summary_weak.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="离线为 scope50 结果补算弱监督关键词指标")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="scope50 数据集路径")
    parser.add_argument("--results", default=str(DEFAULT_RESULTS), help="已有评测结果路径")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="带新指标的结果输出路径")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY), help="新的 summary 输出路径")
    return parser.parse_args()


def normalize_match_text(text: str) -> str:
    return "".join((text or "").lower().split())


def keyword_hit_rate(text: str, keywords: list[str]) -> float:
    normalized_text = normalize_match_text(text)
    cleaned_keywords = [normalize_match_text(keyword) for keyword in (keywords or []) if str(keyword).strip()]
    if not cleaned_keywords:
        return 0.0
    hits = sum(1 for keyword in cleaned_keywords if keyword and keyword in normalized_text)
    return round(hits / len(cleaned_keywords), 4)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def mean_metric(rows: list[dict[str, Any]], metric_name: str) -> float:
    if not rows:
        return 0.0
    values = [float(row["metrics"].get(metric_name, 0.0) or 0.0) for row in rows]
    return round(sum(values) / len(values), 4)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    values = sorted(values)
    idx = (len(values) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(values) - 1)
    frac = idx - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def build_summary(rows: list[dict[str, Any]], dataset_path: Path, results_path: Path) -> dict[str, Any]:
    total = len(rows)
    successes = [row for row in rows if row["metrics"].get("success")]
    latencies = [row["metrics"].get("latency_ms", 0) for row in successes if row["metrics"].get("latency_ms", 0) > 0]
    tokens = [row["metrics"].get("total_tokens", 0) for row in successes if row["metrics"].get("total_tokens", 0) > 0]

    by_type: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("question_type", "unknown")].append(row)

    for key, items in grouped.items():
        by_type[key] = {
            "count": len(items),
            "success_rate": round(sum(1 for item in items if item["metrics"].get("success")) / len(items), 4),
            "citation_rate": mean_metric(items, "citation_rate"),
            "avg_rouge_l_f1": mean_metric(items, "answer_rouge_l_f1"),
            "avg_matched_keywords_hit_rate": mean_metric(items, "matched_keywords_hit_rate"),
            "avg_citation_keyword_hit_rate": mean_metric(items, "citation_keyword_hit_rate"),
        }

    error_counter = Counter()
    for row in rows:
        err = row["metrics"].get("error")
        if err:
            error_counter[json.dumps(err, ensure_ascii=False)] += 1

    return {
        "dataset": str(dataset_path),
        "results": str(results_path),
        "total": total,
        "success_count": len(successes),
        "success_rate": round(len(successes) / total, 4) if total else 0.0,
        "avg_answer_rouge_l_f1": mean_metric(rows, "answer_rouge_l_f1"),
        "citation_rate": mean_metric(rows, "citation_rate"),
        "avg_matched_keywords_hit_rate": mean_metric(rows, "matched_keywords_hit_rate"),
        "avg_citation_keyword_hit_rate": mean_metric(rows, "citation_keyword_hit_rate"),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": round(percentile(latencies, 0.95), 2) if latencies else 0.0,
        "avg_total_tokens": round(sum(tokens) / len(tokens), 2) if tokens else 0.0,
        "by_question_type": by_type,
        "top_errors": error_counter.most_common(10),
    }


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset).expanduser().resolve()
    results_path = Path(args.results).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    summary_path = Path(args.summary).expanduser().resolve()

    dataset_rows = load_jsonl(dataset_path)
    dataset_map = {row["eval_id"]: row for row in dataset_rows}
    result_rows = load_jsonl(results_path)

    enriched_rows: list[dict[str, Any]] = []
    for row in result_rows:
        item = dataset_map.get(row["eval_id"], {})
        matched_keywords = item.get("matched_keywords") or []
        answer = row.get("answer", "")
        citations = row.get("citations", []) or []
        citation_text = "\n".join(
            f"{citation.get('doc_title', '')}\n{citation.get('text', '')}"
            for citation in citations
        )

        row["matched_keywords"] = matched_keywords
        row["bucket"] = item.get("bucket")
        row["expected_behavior"] = item.get("expected_behavior")
        row["metrics"]["matched_keywords_count"] = len(matched_keywords)
        row["metrics"]["matched_keywords_hit_rate"] = keyword_hit_rate(answer, matched_keywords)
        row["metrics"]["citation_keyword_hit_rate"] = keyword_hit_rate(citation_text, matched_keywords)
        enriched_rows.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for row in enriched_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = build_summary(enriched_rows, dataset_path, output_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
