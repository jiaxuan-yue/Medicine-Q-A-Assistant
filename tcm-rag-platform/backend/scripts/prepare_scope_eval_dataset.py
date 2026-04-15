#!/usr/bin/env python3
"""Prepare a scope-aware evaluation dataset for the current herb/bencao corpus."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_CANDIDATES = [
    ROOT / "test_datasets.jsonl",
    ROOT.parent / "test_datasets.jsonl",
    Path.home() / "Downloads" / "test_datasets.jsonl",
]
DEFAULT_OUTPUT = ROOT / "data" / "eval" / "scope50_eval_300.jsonl"
DEFAULT_SUMMARY = ROOT / "data" / "eval" / "scope50_eval_300_summary.json"


HERB_TERMS = [
    "当归", "人参", "黄芪", "党参", "白术", "茯苓", "甘草", "附子", "枸杞", "川芎",
    "黄连", "黄芩", "陈皮", "半夏", "生姜", "大枣", "熟地", "地黄", "白芍", "丹参",
    "防风", "麻黄", "鱼腥草", "西洋参", "红花", "桑葚", "玫瑰", "菊花", "蒲公英",
]

STRONG_TERMS = [
    "本草", "药膳", "食疗", "煲汤", "泡茶", "泡水", "炮制", "炮炙", "性味", "归经", "药性",
] + HERB_TERMS

MEDIUM_TERMS = ["中药", "中医"]

NEGATIVE_TERMS = [
    "医院", "手术", "输液", "退烧药", "抗生素", "青霉素", "阿莫西林", "布洛芬", "甲硝唑",
    "头孢", "奥氮平", "肝素", "CT", "ct", "彩超", "住院", "急诊", "化疗", "放疗", "西药",
]


@dataclass
class EvalItem:
    source_line: int
    question: str
    answer: str
    bucket: str
    matched_keywords: list[str]
    expected_behavior: str

    def to_dict(self, eval_id: int) -> dict:
        return {
            "eval_id": f"scope50-{eval_id:03d}",
            "source_line": self.source_line,
            "question": self.question,
            "reference_answer": self.answer,
            "bucket": self.bucket,
            "matched_keywords": self.matched_keywords,
            "expected_behavior": self.expected_behavior,
        }


def _resolve_source(explicit_source: str | None) -> Path:
    if explicit_source:
        source = Path(explicit_source).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"评测源文件不存在: {source}")
        return source

    for candidate in DEFAULT_SOURCE_CANDIDATES:
        if candidate.exists():
            return candidate

    searched = "\n".join(f"- {path}" for path in DEFAULT_SOURCE_CANDIDATES)
    raise FileNotFoundError(f"未找到 test_datasets.jsonl，可用 --source 指定路径。已检查:\n{searched}")


def _load_items(source: Path) -> tuple[list[EvalItem], list[EvalItem], list[EvalItem]]:
    core: list[EvalItem] = []
    broad: list[EvalItem] = []
    negative: list[EvalItem] = []

    with source.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            question = obj.get("questions", "").strip()
            answer = obj.get("answers", "").strip()
            if not question or not answer:
                continue

            strong_hits = [term for term in STRONG_TERMS if term in question]
            medium_hits = [term for term in MEDIUM_TERMS if term in question]
            negative_hits = [term for term in NEGATIVE_TERMS if term in question]

            if strong_hits and not negative_hits:
                core.append(
                    EvalItem(
                        source_line=idx,
                        question=question,
                        answer=answer,
                        bucket="core_in_scope",
                        matched_keywords=strong_hits[:6],
                        expected_behavior="should retrieve herb/food/paozhi evidence and answer directly",
                    )
                )
            elif medium_hits and not negative_hits:
                broad.append(
                    EvalItem(
                        source_line=idx,
                        question=question,
                        answer=answer,
                        bucket="broad_in_scope",
                        matched_keywords=medium_hits[:4],
                        expected_behavior="can answer if corpus helps; otherwise should stay cautious",
                    )
                )
            elif negative_hits and not strong_hits and not medium_hits:
                negative.append(
                    EvalItem(
                        source_line=idx,
                        question=question,
                        answer=answer,
                        bucket="out_of_scope_negative",
                        matched_keywords=negative_hits[:4],
                        expected_behavior="should avoid fabricated herb citations and prefer low-confidence / medical-safety response",
                    )
                )

    return core, broad, negative


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成适配前 50 本本草/食疗/炮制语料范围的 300 条评测集")
    parser.add_argument("--source", help="原始 jsonl 路径；默认自动尝试项目根目录、上级目录和 ~/Downloads")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="生成的评测集 jsonl 输出路径")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY), help="生成的汇总 json 输出路径")
    parser.add_argument("--limit", type=int, default=300, help="最终输出样本数，默认 300")
    parser.add_argument("--core-limit", type=int, default=72, help="core_in_scope 保留数，默认 72")
    parser.add_argument("--broad-limit", type=int, default=85, help="broad_in_scope 保留数，默认 85")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    source = _resolve_source(args.source)
    output = Path(args.output).expanduser().resolve()
    summary_path = Path(args.summary).expanduser().resolve()

    core, broad, negative = _load_items(source)

    selected_core = core[:args.core_limit]
    selected_broad = broad[:args.broad_limit]
    needed_neg = max(0, args.limit - len(selected_core) - len(selected_broad))
    selected_negative = negative[:needed_neg]

    final_items = selected_core + selected_broad + selected_negative
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8") as f:
        for idx, item in enumerate(final_items, start=1):
            f.write(json.dumps(item.to_dict(idx), ensure_ascii=False) + "\n")

    summary = {
        "source": str(source),
        "output": str(output),
        "total": len(final_items),
        "bucket_counts": {
            "core_in_scope": len(selected_core),
            "broad_in_scope": len(selected_broad),
            "out_of_scope_negative": len(selected_negative),
        },
        "notes": [
            "core_in_scope is the most suitable subset for current herb/bencao retrieval validation.",
            "broad_in_scope keeps some realistic but weaker-alignment traditional medicine questions.",
            "out_of_scope_negative is used to evaluate hallucination control and abstention behavior.",
        ],
    }
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
