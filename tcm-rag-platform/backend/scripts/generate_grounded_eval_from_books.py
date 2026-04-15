#!/usr/bin/env python3
"""Use the current LLM to generate grounded eval data from ancient book source text.

The script:
1. reads the selected books from TCM-Ancient-Books-master
2. chunks the original text with the same chunking strategy as indexing
3. samples representative chunks
4. asks the configured LLM to generate one grounded QA item per chunk
5. saves a JSONL dataset that contains both the generated test item and its gold evidence

Example:
    python backend/scripts/generate_grounded_eval_from_books.py \
      --book-limit 50 \
      --total 300 \
      --output data/eval/book_grounded_eval_300.jsonl
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
from app.services.chunking_service import chunking_service


setup_logging("INFO")
logger = get_logger(__name__)

DEFAULT_BOOKS_DIR = PROJECT_ROOT.parent / "TCM-Ancient-Books-master"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "eval" / "book_grounded_eval_300.jsonl"
DEFAULT_SUMMARY = PROJECT_ROOT / "data" / "eval" / "book_grounded_eval_300_summary.json"

QUESTION_TYPES = [
    "herb_knowledge",
    "food_therapy",
    "paozhi",
    "efficacy",
    "usage",
    "contraindication",
    "book_fact",
]


def get_llm_defaults() -> dict[str, Any]:
    from app.core.config import settings

    return {
        "model": settings.LLM_MODEL,
        "api_key": settings.DASHSCOPE_API_KEY,
    }


@dataclass
class ChunkCandidate:
    book_path: Path
    book_title: str
    chunk_index: int
    section: str
    chunk_text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="基于书本原文生成带 gold evidence 的测试集")
    parser.add_argument("--books-dir", default=str(DEFAULT_BOOKS_DIR), help="古籍 txt 目录")
    parser.add_argument("--book-limit", type=int, default=50, help="使用前多少本书，默认 50")
    parser.add_argument("--total", type=int, default=300, help="总共生成多少条评测数据，默认 300")
    parser.add_argument("--chunk-size", type=int, default=900, help="生成评测候选时的 chunk 长度，默认 900")
    parser.add_argument("--overlap", type=int, default=100, help="生成评测候选时的 overlap，默认 100")
    parser.add_argument("--model", help="指定生成测试集时使用的大模型，不填则使用当前默认模型")
    parser.add_argument("--temperature", type=float, default=0.3, help="生成温度，默认 0.3")
    parser.add_argument("--max-tokens", type=int, default=900, help="单次生成最大 token，默认 900")
    parser.add_argument("--sleep", type=float, default=0.2, help="每次请求后 sleep 秒数，默认 0.2")
    parser.add_argument("--concurrency", type=int, default=5, help="并发生成数，默认 5")
    parser.add_argument("--seed", type=int, default=42, help="随机种子，默认 42")
    parser.add_argument("--retries", type=int, default=3, help="单条生成失败时的重试次数，默认 3")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="输出 jsonl 路径")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY), help="输出 summary json 路径")
    parser.add_argument("--resume", action="store_true", help="若输出文件已存在，则跳过已生成的 chunk")
    return parser.parse_args()


def normalize_title(book_path: Path) -> str:
    stem = book_path.stem
    parts = stem.split("-", 1)
    return parts[1] if len(parts) == 2 else stem


def load_books(books_dir: Path, book_limit: int) -> list[Path]:
    books = sorted(books_dir.glob("*.txt"))
    if not books:
        raise FileNotFoundError(f"未找到古籍 txt 文件: {books_dir}")
    return books[:book_limit]


def pick_spread_indices(total_chunks: int, needed: int) -> list[int]:
    if total_chunks <= 0 or needed <= 0:
        return []
    if needed >= total_chunks:
        return list(range(total_chunks))

    indices: list[int] = []
    used: set[int] = set()
    step = total_chunks / needed
    for i in range(needed):
        idx = min(total_chunks - 1, int((i + 0.5) * step))
        while idx in used and idx + 1 < total_chunks:
            idx += 1
        while idx in used and idx - 1 >= 0:
            idx -= 1
        if idx not in used:
            used.add(idx)
            indices.append(idx)
    return sorted(indices)


def load_existing_keys(output_path: Path) -> tuple[set[str], int]:
    if not output_path.exists():
        return set(), 0
    seen: set[str] = set()
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
            key = obj.get("source_key")
            if key:
                seen.add(key)
            count += 1
    return seen, count


def build_candidates(
    *,
    books: list[Path],
    total: int,
    chunk_size: int,
    overlap: int,
) -> list[ChunkCandidate]:
    per_book = math.ceil(total / len(books))
    candidates: list[ChunkCandidate] = []

    for book_path in books:
        text = book_path.read_text("utf-8", errors="ignore")
        chunks = chunking_service.chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        if not chunks:
            continue
        indices = pick_spread_indices(len(chunks), per_book)
        for idx in indices:
            chunk = chunks[idx]
            metadata = chunk.get("metadata_json", {}) or {}
            candidates.append(
                ChunkCandidate(
                    book_path=book_path,
                    book_title=normalize_title(book_path),
                    chunk_index=chunk["chunk_index"],
                    section=metadata.get("section", ""),
                    chunk_text=chunk["chunk_text"],
                )
            )

    return candidates[:total]


def build_messages(candidate: ChunkCandidate) -> list[dict]:
    schema = {
        "question": "自然、像真实用户会问的问题，不要直接照抄标题",
        "reference_answer": "只能依据材料回答，2-4 句，避免扩展到材料以外",
        "question_type": f"必须从 {QUESTION_TYPES} 中选一个",
        "difficulty": "easy 或 medium 或 hard",
        "keywords": ["2-6 个与问题相关的实体或关键词"],
        "supported_facts": ["2-4 条可直接从材料抽出的事实"],
    }
    return [
        {
            "role": "system",
            "content": (
                "你是中医古籍评测集构建助手。"
                "你必须严格基于给定原文生成 1 条测试样本。"
                "不要引用材料中没有出现的知识，不要生成无法被原文支持的问题。"
                "输出必须是单个 JSON 对象，不能加 markdown。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"书名：{candidate.book_title}\n"
                f"章节：{candidate.section or '未标注'}\n"
                "原文片段：\n"
                f"{candidate.chunk_text}\n\n"
                "请你基于这段原文，构造 1 条适合 RAG 检索+生成评测的测试样本。\n"
                "要求：\n"
                "1. 问题要尽量贴近真实用户表达，可以做适度口语化改写。\n"
                "2. 问题必须能主要靠这段原文回答。\n"
                "3. 参考答案必须严格受原文支持，不能臆造。\n"
                "4. 如果材料更适合做药物功效、食疗、炮制、用法、禁忌、古籍事实类问题，请优先选择这些方向。\n"
                "5. 输出 JSON 对象字段必须包含：question, reference_answer, question_type, difficulty, keywords, supported_facts。\n"
                f"字段说明：{json.dumps(schema, ensure_ascii=False)}"
            ),
        },
    ]


def extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError("未找到 JSON 对象")
    return json.loads(match.group(0))


def normalize_generated(payload: dict) -> dict:
    question = str(payload.get("question", "")).strip()
    reference_answer = str(payload.get("reference_answer", "")).strip()
    question_type = str(payload.get("question_type", "")).strip()
    difficulty = str(payload.get("difficulty", "")).strip().lower()
    keywords = payload.get("keywords") or []
    supported_facts = payload.get("supported_facts") or []

    if not question or not reference_answer:
        raise ValueError("question/reference_answer 为空")
    if question_type not in QUESTION_TYPES:
        question_type = "book_fact"
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"
    if not isinstance(keywords, list):
        keywords = []
    if not isinstance(supported_facts, list):
        supported_facts = []

    return {
        "question": question,
        "reference_answer": reference_answer,
        "question_type": question_type,
        "difficulty": difficulty,
        "keywords": [str(x).strip() for x in keywords if str(x).strip()][:6],
        "supported_facts": [str(x).strip() for x in supported_facts if str(x).strip()][:4],
    }


async def generate_one(
    candidate: ChunkCandidate,
    *,
    default_model: str,
    api_key: str,
    model: str | None,
    temperature: float,
    max_tokens: int,
    retries: int,
) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            raw = await asyncio.to_thread(
                _call_llm_sync,
                build_messages(candidate),
                model or default_model,
                temperature,
                max_tokens,
                api_key,
            )
            return normalize_generated(extract_json(raw))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "生成失败: %s [chunk=%s/%s, attempt=%d/%d]",
                candidate.book_title,
                candidate.book_path.name,
                candidate.chunk_index,
                attempt,
                retries,
            )
            await asyncio.sleep(0.8 * attempt)
    assert last_error is not None
    raise last_error


def _call_llm_sync(
    messages: list[dict],
    model: str,
    temperature: float,
    max_tokens: int,
    api_key: str,
) -> str:
    import dashscope
    from dashscope import Generation

    if not (api_key or "").strip():
        raise RuntimeError("DashScope API key 未配置，请在 .env 中设置有效的 DASHSCOPE_API_KEY")

    dashscope.api_key = api_key
    response = Generation.call(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        result_format="message",
    )
    if response.status_code == 200:
        return response.output.choices[0].message.content
    raise RuntimeError(f"LLM API error: {response.code} - {response.message}")


async def main_async(args: argparse.Namespace) -> None:
    llm_defaults = get_llm_defaults()
    books_dir = Path(args.books_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    summary_path = Path(args.summary).expanduser().resolve()

    books = load_books(books_dir, args.book_limit)
    candidates = build_candidates(
        books=books,
        total=args.total,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )
    if not candidates:
        raise RuntimeError("未选出任何候选 chunk")

    seen_keys: set[str] = set()
    existing_count = 0
    if args.resume:
        seen_keys, existing_count = load_existing_keys(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.resume and output_path.exists() else "w"
    question_seen: set[str] = set()
    bucket_counts: dict[str, int] = {}
    generated = 0
    skipped_existing = 0

    if args.resume and output_path.exists():
        with output_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                q = obj.get("question")
                if q:
                    question_seen.add(q)
                qt = obj.get("question_type")
                if qt:
                    bucket_counts[qt] = bucket_counts.get(qt, 0) + 1

    pending_candidates: list[ChunkCandidate] = []
    for candidate in candidates:
        source_key = f"{candidate.book_path.name}#{candidate.chunk_index}"
        if source_key in seen_keys:
            skipped_existing += 1
            continue
        pending_candidates.append(candidate)

    semaphore = asyncio.Semaphore(max(1, args.concurrency))

    async def _worker(candidate: ChunkCandidate) -> tuple[ChunkCandidate, dict]:
        async with semaphore:
            item = await generate_one(
                candidate,
                default_model=llm_defaults["model"],
                api_key=llm_defaults["api_key"],
                model=args.model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                retries=args.retries,
            )
            await asyncio.sleep(args.sleep)
            return candidate, item

    tasks = [asyncio.create_task(_worker(candidate)) for candidate in pending_candidates]

    with output_path.open(mode, encoding="utf-8") as fout:
        for finished in asyncio.as_completed(tasks):
            candidate, item = await finished
            if item["question"] in question_seen:
                logger.info("跳过重复问题: %s", item["question"])
                continue

            eval_id = f"book-grounded-{existing_count + generated + 1:03d}"
            row = {
                "eval_id": eval_id,
                "question": item["question"],
                "reference_answer": item["reference_answer"],
                "question_type": item["question_type"],
                "difficulty": item["difficulty"],
                "keywords": item["keywords"],
                "supported_facts": item["supported_facts"],
                "gold_book_title": candidate.book_title,
                "gold_book_file": candidate.book_path.name,
                "gold_chunk_index": candidate.chunk_index,
                "gold_section": candidate.section,
                "gold_chunk_text": candidate.chunk_text,
                "source_key": f"{candidate.book_path.name}#{candidate.chunk_index}",
                "generator_model": args.model or llm_defaults["model"],
            }
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            fout.flush()

            question_seen.add(item["question"])
            bucket_counts[item["question_type"]] = bucket_counts.get(item["question_type"], 0) + 1
            generated += 1

            logger.info(
                "已生成 %d/%d: %s [%s | %s]",
                generated + existing_count,
                existing_count + len(pending_candidates),
                candidate.book_title,
                item["question_type"],
                item["difficulty"],
            )

    summary = {
        "books_dir": str(books_dir),
        "book_limit": args.book_limit,
        "books_used": [normalize_title(book) for book in books],
        "requested_total": args.total,
        "candidate_count": len(candidates),
        "generated_now": generated,
        "existing_before_resume": existing_count,
        "skipped_existing": skipped_existing,
        "concurrency": args.concurrency,
        "output": str(output_path),
        "question_type_counts": bucket_counts,
        "generator_model": args.model or llm_defaults["model"],
        "chunk_size": args.chunk_size,
        "overlap": args.overlap,
        "seed": args.seed,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
