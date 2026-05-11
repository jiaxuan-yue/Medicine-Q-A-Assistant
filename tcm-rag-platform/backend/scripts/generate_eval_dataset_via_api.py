#!/usr/bin/env python3
"""Generate a cleaner grounded eval dataset by calling the configured LLM API.

Compared with the older generator, this script:
1. reads from persisted FAISS metadata instead of raw source txt
2. samples cleaner entity-centric chunks from the indexed corpus
3. diversifies user question styles via scenario blueprints
4. outputs a JSONL dataset compatible with run_grounded_eval.py / run_full_eval.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.logger import get_logger, setup_logging
from app.integrations.llm_client import llm_client
from app.services.local_recall_utils import extract_heading_entity


setup_logging("INFO")
logger = get_logger(__name__)

DEFAULT_METADATA = PROJECT_ROOT / "data" / "processed" / "faiss_index" / "metadata.pkl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "eval" / "api_generated_grounded_eval.jsonl"
DEFAULT_SUMMARY = PROJECT_ROOT / "data" / "eval" / "api_generated_grounded_eval_summary.json"

QUESTION_TYPES = [
    "herb_knowledge",
    "food_therapy",
    "paozhi",
    "efficacy",
    "usage",
    "contraindication",
    "book_fact",
]

SCENARIO_BLUEPRINTS = [
    {
        "name": "direct_fact",
        "instruction": "生成一个直接知识问句，用户明确询问某味药或条目的功效、主治或特点。",
        "style_hint": "表达清楚直接，不要过分学术。",
        "preferred_types": ["efficacy", "usage", "book_fact"],
    },
    {
        "name": "colloquial_lookup",
        "instruction": "生成一个更口语化的真实用户问法，可以带“这种药”“这个东西”“古书里怎么说”之类表达。",
        "style_hint": "像普通用户在聊天窗口里提问，不要太书面。",
        "preferred_types": ["efficacy", "herb_knowledge", "book_fact"],
    },
    {
        "name": "book_grounded",
        "instruction": "生成一个明确点名古籍出处的问句，强调“这本书里是怎么记载的”。",
        "style_hint": "问题中自然包含书名。",
        "preferred_types": ["book_fact", "usage", "contraindication"],
    },
    {
        "name": "practical_use",
        "instruction": "如果材料支持，生成一个偏实用的问题，比如怎么用、有什么禁忌、适合什么情况。",
        "style_hint": "避免编造现代医疗场景，只围绕原文支持的用途。",
        "preferred_types": ["usage", "contraindication", "paozhi"],
    },
]

GENERIC_HEADINGS = {
    "上经",
    "中经",
    "下经",
    "上品",
    "中品",
    "下品",
    "邵序",
    "张序",
    "孙序",
    "序",
    "目录",
}


@dataclass
class ChunkCandidate:
    doc_title: str
    chunk_id: str
    chunk_index: int
    section: str
    heading_entity: str
    chunk_text: str
    blueprint: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="调用 LLM API 自动生成更合理的 grounded eval 数据集")
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA), help="FAISS metadata.pkl 路径")
    parser.add_argument("--total", type=int, default=120, help="目标生成条数")
    parser.add_argument("--book-limit", type=int, default=40, help="最多覆盖多少本书")
    parser.add_argument("--min-chars", type=int, default=160, help="最短 chunk 长度")
    parser.add_argument("--max-chars", type=int, default=950, help="最长 chunk 长度")
    parser.add_argument("--model", help="指定生成模型，不填则使用当前默认模型")
    parser.add_argument("--temperature", type=float, default=0.4, help="生成温度")
    parser.add_argument("--max-tokens", type=int, default=1000, help="单次生成最大 token")
    parser.add_argument("--concurrency", type=int, default=4, help="并发生成数")
    parser.add_argument("--sleep", type=float, default=0.2, help="每次请求后 sleep 秒数")
    parser.add_argument("--retries", type=int, default=3, help="生成失败重试次数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="输出 jsonl 路径")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY), help="输出 summary 路径")
    parser.add_argument("--resume", action="store_true", help="若输出文件存在，则跳过已有 source_key")
    return parser.parse_args()


def load_metadata(path: Path) -> list[dict]:
    import pickle

    with path.open("rb") as f:
        return pickle.load(f)


def load_existing(output_path: Path) -> tuple[set[str], set[str], int]:
    if not output_path.exists():
        return set(), set(), 0
    source_keys: set[str] = set()
    questions: set[str] = set()
    count = 0
    with output_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("source_key"):
                source_keys.add(str(obj["source_key"]))
            if obj.get("question"):
                questions.add(str(obj["question"]).strip())
            count += 1
    return source_keys, questions, count


def _looks_usable_text(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if "�" in cleaned:
        return False
    if len(cleaned) < 80:
        return False
    return True


def build_candidates(
    metadata: list[dict],
    *,
    total: int,
    book_limit: int,
    min_chars: int,
    max_chars: int,
) -> list[ChunkCandidate]:
    per_book_limit = max(1, math.ceil(total / max(1, book_limit)))
    grouped: dict[str, list[ChunkCandidate]] = {}

    for item in metadata:
        doc_title = str(item.get("doc_title") or "").strip()
        chunk_id = str(item.get("chunk_id") or "").strip()
        chunk_text = str(item.get("chunk_text") or "")
        meta = item.get("metadata") or {}
        section = str(meta.get("section") or "").strip()
        heading_entity = extract_heading_entity(chunk_text)
        if not doc_title or not chunk_id or not _looks_usable_text(chunk_text):
            continue
        if len(chunk_text) < min_chars or len(chunk_text) > max_chars:
            continue
        if not heading_entity or heading_entity in GENERIC_HEADINGS:
            continue
        if "味" not in chunk_text and "主" not in chunk_text and "治" not in chunk_text:
            continue

        bucket = grouped.setdefault(doc_title, [])
        if len(bucket) >= per_book_limit:
            continue

        blueprint = SCENARIO_BLUEPRINTS[len(bucket) % len(SCENARIO_BLUEPRINTS)]
        bucket.append(
            ChunkCandidate(
                doc_title=doc_title,
                chunk_id=chunk_id,
                chunk_index=int(meta.get("position", 0) or 0),
                section=section,
                heading_entity=heading_entity,
                chunk_text=chunk_text,
                blueprint=blueprint,
            )
        )

    selected_books = sorted(grouped.keys())[:book_limit]
    candidates: list[ChunkCandidate] = []
    for book in selected_books:
        candidates.extend(grouped[book])

    candidates.sort(key=lambda item: (item.doc_title, item.chunk_index, item.heading_entity))
    return candidates[:total]


def build_messages(candidate: ChunkCandidate) -> list[dict]:
    schema = {
        "question": "真实用户提问，不能照抄原文标题",
        "reference_answer": "严格基于原文，2-4 句",
        "question_type": f"只能从 {QUESTION_TYPES} 中选一个",
        "difficulty": "easy 或 medium 或 hard",
        "keywords": ["2-6 个关键词"],
        "matched_keywords": ["与答案和引用最相关的 2-6 个关键词"],
        "supported_facts": ["2-4 条能直接从原文摘出的事实"],
    }

    preferred_types = " / ".join(candidate.blueprint["preferred_types"])
    return [
        {
            "role": "system",
            "content": (
                "你是中医古籍 RAG 评测集设计助手。"
                "你的任务是基于给定原文，生成一条更像真实用户会问的问题。"
                "必须严格 grounded，不能使用原文外知识，不能编造现代适应症。"
                "输出必须是单个 JSON 对象，不要加 markdown。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"书名：{candidate.doc_title}\n"
                f"条目：{candidate.heading_entity}\n"
                f"章节：{candidate.section or '未标注'}\n"
                f"场景类型：{candidate.blueprint['name']}\n"
                f"场景要求：{candidate.blueprint['instruction']}\n"
                f"风格提示：{candidate.blueprint['style_hint']}\n"
                f"优先问题类型：{preferred_types}\n\n"
                "原文片段：\n"
                f"{candidate.chunk_text}\n\n"
                "请生成 1 条评测样本，要求：\n"
                "1. 问题必须可主要依赖这段原文回答。\n"
                "2. 问题不要生硬照抄“某某内容”。\n"
                "3. 参考答案必须只基于原文，不许外推。\n"
                "4. supported_facts 必须是原文中能直接找到依据的短事实。\n"
                "5. matched_keywords 应该选择最适合后续评测命中率统计的词。\n"
                "6. 如果原文明显是药物条目，优先围绕功效、主治、用法、禁忌来问。\n"
                f"输出字段说明：{json.dumps(schema, ensure_ascii=False)}"
            ),
        },
    ]


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("未找到可解析的 JSON 对象")


def normalize_generated(payload: dict[str, Any]) -> dict[str, Any]:
    question = str(payload.get("question", "")).strip()
    reference_answer = str(payload.get("reference_answer", "")).strip()
    question_type = str(payload.get("question_type", "")).strip()
    difficulty = str(payload.get("difficulty", "")).strip().lower()
    keywords = payload.get("keywords") or []
    matched_keywords = payload.get("matched_keywords") or []
    supported_facts = payload.get("supported_facts") or []

    if not question or not reference_answer:
        raise ValueError("question/reference_answer 为空")
    if question_type not in QUESTION_TYPES:
        question_type = "book_fact"
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"
    if not isinstance(keywords, list):
        keywords = []
    if not isinstance(matched_keywords, list):
        matched_keywords = []
    if not isinstance(supported_facts, list):
        supported_facts = []

    clean_keywords = [str(x).strip() for x in keywords if str(x).strip()][:6]
    clean_matched = [str(x).strip() for x in matched_keywords if str(x).strip()][:6]
    clean_facts = [str(x).strip() for x in supported_facts if str(x).strip()][:4]
    if not clean_matched:
        clean_matched = clean_keywords[:]

    return {
        "question": question,
        "reference_answer": reference_answer,
        "question_type": question_type,
        "difficulty": difficulty,
        "keywords": clean_keywords,
        "matched_keywords": clean_matched,
        "supported_facts": clean_facts,
    }


async def generate_one(
    candidate: ChunkCandidate,
    *,
    model: str | None,
    temperature: float,
    max_tokens: int,
    retries: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            raw = await llm_client.chat(
                build_messages(candidate),
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return normalize_generated(extract_json(raw))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "生成失败: %s [%s attempt=%d/%d]",
                candidate.doc_title,
                candidate.heading_entity,
                attempt,
                retries,
            )
            await asyncio.sleep(0.8 * attempt)
    assert last_error is not None
    raise last_error


async def main_async(args: argparse.Namespace) -> None:
    random.seed(args.seed)
    metadata_path = Path(args.metadata).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    summary_path = Path(args.summary).expanduser().resolve()

    metadata = load_metadata(metadata_path)
    random.shuffle(metadata)
    candidates = build_candidates(
        metadata,
        total=args.total,
        book_limit=args.book_limit,
        min_chars=args.min_chars,
        max_chars=args.max_chars,
    )
    if not candidates:
        raise RuntimeError("未选出任何可用候选 chunk")

    seen_source_keys: set[str] = set()
    seen_questions: set[str] = set()
    existing_count = 0
    if args.resume:
        seen_source_keys, seen_questions, existing_count = load_existing(output_path)

    pending: list[ChunkCandidate] = []
    for candidate in candidates:
        source_key = f"{candidate.doc_title}#{candidate.chunk_id}"
        if source_key in seen_source_keys:
            continue
        pending.append(candidate)

    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    mode = "a" if args.resume and output_path.exists() else "w"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generated = 0
    scenario_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    used_books: set[str] = set()

    async def _worker(candidate: ChunkCandidate) -> tuple[ChunkCandidate, dict[str, Any]]:
        async with semaphore:
            item = await generate_one(
                candidate,
                model=args.model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                retries=args.retries,
            )
            await asyncio.sleep(args.sleep)
            return candidate, item

    tasks = [asyncio.create_task(_worker(candidate)) for candidate in pending]

    with output_path.open(mode, encoding="utf-8") as fout:
        for finished in asyncio.as_completed(tasks):
            candidate, item = await finished
            if item["question"] in seen_questions:
                logger.info("跳过重复问题: %s", item["question"])
                continue

            eval_id = f"api-grounded-{existing_count + generated + 1:03d}"
            row = {
                "eval_id": eval_id,
                "question": item["question"],
                "reference_answer": item["reference_answer"],
                "question_type": item["question_type"],
                "difficulty": item["difficulty"],
                "keywords": item["keywords"],
                "matched_keywords": item["matched_keywords"],
                "supported_facts": item["supported_facts"],
                "gold_book_title": candidate.doc_title,
                "gold_book_file": "",
                "gold_chunk_index": candidate.chunk_index,
                "gold_section": candidate.section,
                "gold_chunk_text": candidate.chunk_text,
                "gold_chunk_id": candidate.chunk_id,
                "source_key": f"{candidate.doc_title}#{candidate.chunk_id}",
                "generator_model": args.model or llm_client.model,
                "scenario_type": candidate.blueprint["name"],
                "heading_entity": candidate.heading_entity,
            }
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            fout.flush()

            seen_questions.add(item["question"])
            generated += 1
            used_books.add(candidate.doc_title)
            scenario = candidate.blueprint["name"]
            scenario_counts[scenario] = scenario_counts.get(scenario, 0) + 1
            qtype = item["question_type"]
            type_counts[qtype] = type_counts.get(qtype, 0) + 1

            logger.info(
                "已生成 %d/%d: %s | %s | %s",
                existing_count + generated,
                existing_count + len(pending),
                candidate.doc_title,
                scenario,
                qtype,
            )

    summary = {
        "metadata": str(metadata_path),
        "requested_total": args.total,
        "candidate_count": len(candidates),
        "generated_now": generated,
        "existing_before_resume": existing_count,
        "books_used_count": len(used_books),
        "books_used": sorted(used_books),
        "scenario_counts": scenario_counts,
        "question_type_counts": type_counts,
        "output": str(output_path),
        "generator_model": args.model or llm_client.model,
        "temperature": args.temperature,
        "concurrency": args.concurrency,
        "seed": args.seed,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
