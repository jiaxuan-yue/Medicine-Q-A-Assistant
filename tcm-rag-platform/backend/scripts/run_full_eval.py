#!/usr/bin/env python3
"""端到端 RAG 评测脚本 —— 检索 + 生成 + 忠实度 + 幻觉 + 事实覆盖。

对比旧版 `run_grounded_eval.py`，新增：
- LLM Judge 忠实度（answer claims 是否都能在 gold_chunk 中找到依据）
- 事实覆盖率（supported_facts 有多少条被 answer 提及）
- 幻觉检测（answer 中是否有 gold_chunk 之外的编造内容）
- 谨慎度评分（对不确定的部分是否做了风险提示）
- 检索侧诊断指标（各通道召回数、融合数）

用法：
    python backend/scripts/run_full_eval.py \\
        --base-url http://127.0.0.1:8000 \\
        --dataset data/eval/book_grounded_eval_300.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = PROJECT_ROOT / "data" / "eval" / "book_grounded_eval_300.jsonl"
DEFAULT_RESULTS = PROJECT_ROOT / "data" / "eval" / "full_eval_results.jsonl"
DEFAULT_SUMMARY = PROJECT_ROOT / "data" / "eval" / "full_eval_summary.json"
_ABSTAIN_MARKERS = (
    "未检索到",
    "未找到",
    "无法确定",
    "无法判断",
    "不确定",
    "请确认",
    "暂无明确记载",
    "没有直接对应",
    "可能是输入",
)


@dataclass
class EvalClient:
    base_url: str
    timeout: float
    session: requests.Session
    access_token: str | None = None

    @property
    def api_base(self) -> str:
        return self.base_url.rstrip("/") + "/api/v1"

    def set_token(self, token: str) -> None:
        self.access_token = token
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = path if path.startswith("http") else f"{self.api_base}{path}"
        kwargs.setdefault("timeout", self.timeout)
        return self.session.request(method, url, **kwargs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="端到端 RAG 评测：检索 + 生成 + 忠实度 + 幻觉 + 事实覆盖")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--username", default="eval_runner")
    parser.add_argument("--password", default="EvalRunner123")
    parser.add_argument("--email", default="eval_runner@tcm.local")
    parser.add_argument("--profile-name", default="评测角色")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--sleep", type=float, default=0.1)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--llm-judge", action="store_true", help="启用 LLM Judge 评分（忠实度/幻觉/谨慎度）")
    parser.add_argument("--judge-model", default="qwen-plus", help="LLM Judge 使用的模型")
    return parser.parse_args()


# ── helpers ─────────────────────────────────────────────────

def load_dataset(path: Path, limit: int | None = None) -> list[dict]:
    items: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
            if limit and len(items) >= limit:
                break
    return items


def load_done_ids(results_path: Path) -> set[str]:
    if not results_path.exists():
        return set()
    done: set[str] = set()
    with results_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            eval_id = obj.get("eval_id")
            if eval_id:
                done.add(str(eval_id))
    return done


def safe_json(response: requests.Response) -> dict[str, Any]:
    try:
        return response.json()
    except Exception as exc:
        raise RuntimeError(f"接口返回非 JSON: {response.status_code} {response.text[:300]}") from exc


def ensure_ok(response: requests.Response) -> dict[str, Any]:
    payload = safe_json(response)
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {payload}")
    if payload.get("code") != 0:
        raise RuntimeError(f"业务错误: {payload}")
    return payload


def login_or_register(client: EvalClient, username: str, password: str, email: str) -> None:
    login_response = client.request("POST", "/auth/login", json={"username": username, "password": password})
    if login_response.status_code == 200:
        client.set_token(ensure_ok(login_response)["data"]["access_token"])
        return

    register_response = client.request(
        "POST", "/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    if register_response.status_code == 200:
        client.set_token(ensure_ok(register_response)["data"]["access_token"])
        return

    raise RuntimeError(
        f"登录/注册均失败。\nlogin={login_response.status_code}\nregister={register_response.status_code}"
    )


def ensure_case_profile(client: EvalClient, profile_name: str) -> int:
    resp = ensure_ok(client.request("GET", "/case-profiles"))
    items = resp.get("data") or []
    for item in items:
        if item.get("profile_name") == profile_name and item.get("profile_completed"):
            return int(item["id"])

    payload = {
        "profile_name": profile_name,
        "gender": "女",
        "age": 30,
        "height_cm": 165,
        "weight_kg": 55,
        "medical_history": "无特殊既往史",
        "allergy_history": "无",
        "current_medications": "无",
        "menstrual_history": "规律",
        "notes": "仅用于自动化评测",
        "tags": ["eval", "automation"],
    }
    created = ensure_ok(client.request("POST", "/case-profiles", json=payload))
    return int(created["data"]["id"])


def create_session(client: EvalClient, case_profile_id: int, title: str) -> str:
    resp = ensure_ok(
        client.request("POST", "/chats", json={"title": title, "case_profile_id": case_profile_id})
    )
    return str(resp["data"]["session_id"])


def parse_sse_response(response: requests.Response) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    current_event: str | None = None
    data_lines: list[str] = []

    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        line = raw_line.strip()
        if not line:
            if current_event:
                raw_data = "\n".join(data_lines).strip()
                try:
                    payload = json.loads(raw_data) if raw_data else {}
                except json.JSONDecodeError:
                    payload = {"raw": raw_data}
                events.append({"event": current_event, "data": payload})
            current_event = None
            data_lines = []
            continue
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())

    answer_parts: list[str] = []
    citations: list[dict[str, Any]] = []
    done_payload: dict[str, Any] = {}
    error_payload: dict[str, Any] = {}

    for item in events:
        event = item["event"]
        payload = item["data"]
        if event == "chunk":
            content = payload.get("content", "")
            if content:
                answer_parts.append(str(content))
        elif event == "citation":
            citations = payload.get("citations", []) or []
        elif event == "done":
            done_payload = payload
        elif event == "error":
            error_payload = payload

    return {
        "events": events,
        "answer": "".join(answer_parts).strip(),
        "citations": citations,
        "done": done_payload,
        "error": error_payload,
    }


def stream_chat(client: EvalClient, session_id: str, query: str) -> dict[str, Any]:
    response = client.request(
        "POST", f"/chats/{session_id}/stream", json={"query": query}, stream=True,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"流式问答失败: {response.status_code} {response.text[:300]}")
    return parse_sse_response(response)


# ── LLM Judge ───────────────────────────────────────────────

_JUDGE_PROMPT = """\
你是一名中医药 RAG 系统的评测专家。请根据以下标准对系统生成的回答进行评分：

【输入信息】
- 用户问题：{question}
- 标准答案：{reference_answer}
- 原始依据（gold_chunk）：{gold_chunk_text}
- 系统生成的回答：{answer}
- 系统引用的文献：{citations_info}
- 预定义支持的事实（supported_facts）：{supported_facts}

【评分维度】

1. faithful_score (1-5): 忠实度
   - 5: 回答中所有关键信息都能在 gold_chunk 中找到依据，无编造
   - 4: 大部分内容有依据，极少量无法确认但不影响整体
   - 3: 约一半内容有依据，部分无法在 gold_chunk 中确认
   - 2: 大部分内容无法在 gold_chunk 中找到依据
   - 1: 几乎全是编造，与 gold_chunk 无关

2. hallucination_score (0-1): 幻觉程度（1=严重幻觉，0=无幻觉）
   - 回答中是否包含 gold_chunk 中不存在的"事实性陈述"
   - 注意：风险提示/免责声明/建议咨询医生不算幻觉

3. fact_coverage (0-1): 事实覆盖率
   - 预定义的 supported_facts 中有多少条被回答提及或覆盖
   - 语义相同即可，不要求原文复述

4. caution_score (1-5): 谨慎度
   - 5: 对不确定内容明确标注了局限性，建议就医，不做诊断
   - 3: 有基本风险提示，但部分表述过于肯定
   - 1: 没有任何谨慎表述，直接给结论

请以纯 JSON 格式输出，不要附加任何解释。字段为：
faithful_score, hallucination_score, fact_coverage, caution_score, faithful_reason, hallucination_reason, fact_coverage_details, caution_reason
"""


def run_llm_judge(
    question: str,
    reference_answer: str,
    gold_chunk_text: str,
    answer: str,
    citations: list[dict],
    supported_facts: list[str],
    base_url: str,
    timeout: float,
    model: str,
    access_token: str,
) -> dict[str, Any] | None:
    """调用 LLM 做忠实度/幻觉/事实覆盖/谨慎度四维评分。"""
    try:
        from app.integrations.llm_client import llm_client as _llm_client
    except ImportError:
        # 离线模式，用 requests 直接调
        return _run_llm_judge_http(
            question, reference_answer, gold_chunk_text, answer,
            citations, supported_facts, base_url, timeout, model, access_token,
        )

    # 在线模式，通过 llm_client
    citations_info = "\n".join(
        f"- {c.get('doc_title', '')}: {c.get('text', '')[:100]}"
        for c in (citations or [])[:5]
    )
    facts_text = "\n".join(f"- {f}" for f in (supported_facts or []))
    prompt = _JUDGE_PROMPT.format(
        question=question,
        reference_answer=reference_answer,
        gold_chunk_text=gold_chunk_text[:3000],
        answer=answer[:3000],
        citations_info=citations_info,
        supported_facts=facts_text,
    )
    # This would need to be run async, so we'll use the HTTP fallback for sync
    return _run_llm_judge_http(
        question, reference_answer, gold_chunk_text, answer,
        citations, supported_facts, base_url, timeout, model, access_token,
    )


def _run_llm_judge_http(
    question: str,
    reference_answer: str,
    gold_chunk_text: str,
    answer: str,
    citations: list[dict],
    supported_facts: list[str],
    base_url: str,
    timeout: float,
    model: str,
    access_token: str,
) -> dict[str, Any] | None:
    """通过 HTTP 调用 LLM API 做 judge。"""
    citations_info = "\n".join(
        f"- {c.get('doc_title', '')}: {c.get('text', '')[:100]}"
        for c in (citations or [])[:5]
    )
    facts_text = "\n".join(f"- {f}" for f in (supported_facts or []))
    prompt = _JUDGE_PROMPT.format(
        question=question,
        reference_answer=reference_answer,
        gold_chunk_text=gold_chunk_text[:3000],
        answer=answer[:3000],
        citations_info=citations_info,
        supported_facts=facts_text,
    )

    # Try the backend's own API first (it proxies to the LLM)
    session = requests.Session()
    try:
        # Check if backend has a judge endpoint
        resp = session.request(
            "POST",
            f"{base_url.rstrip('/')}/api/v1/llm/judge",
            json={
                "prompt": prompt,
                "model": model,
                "temperature": 0.1,
                "max_tokens": 500,
            },
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            raw = data.get("data", {}).get("text", data.get("data", ""))
            return _parse_judge_response(raw)
    except Exception:
        pass
    finally:
        session.close()

    # If no judge endpoint, try calling DashScope directly
    return _call_dashscope_judge(prompt, model, timeout)


def _call_dashscope_judge(
    prompt: str,
    model: str,
    timeout: float,
) -> dict[str, Any] | None:
    """直接调用 DashScope API。"""
    import os

    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return None

    base_url = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    session = requests.Session()
    try:
        resp = session.post(
            f"{base_url}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 500,
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            return _parse_judge_response(raw)
    except Exception as exc:
        print(f"  LLM Judge 调用失败: {exc}")
    finally:
        session.close()
    return None


def _parse_judge_response(raw: str) -> dict[str, Any] | None:
    """从 LLM 输出中提取 JSON 评分。"""
    raw = raw.strip()
    # Strip markdown fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    # Find JSON block
    match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


# ── metric computation ──────────────────────────────────────

def tokenize(text: str) -> list[str]:
    text = text or ""
    tokens: list[str] = []
    buff: list[str] = []
    for char in text:
        if char.isalnum():
            buff.append(char.lower())
        else:
            if buff:
                tokens.append("".join(buff))
                buff = []
            if "\u4e00" <= char <= "\u9fff":
                tokens.append(char)
    if buff:
        tokens.append("".join(buff))
    return tokens


def evidence_overlap_score(citation_text: str, gold_chunk_text: str) -> float:
    c = "".join((citation_text or "").split())
    g = "".join((gold_chunk_text or "").split())
    if not c or not g:
        return 0.0
    if c in g or g in c:
        return 1.0
    match = SequenceMatcher(None, c, g).find_longest_match(0, len(c), 0, len(g))
    if len(c) == 0:
        return 0.0
    return match.size / len(c)


def normalize_match_text(text: str) -> str:
    return "".join((text or "").lower().split())


def keyword_hit_rate(text: str, keywords: list[str]) -> float:
    normalized_text = normalize_match_text(text)
    cleaned_keywords = [normalize_match_text(kw) for kw in (keywords or []) if str(kw).strip()]
    if not cleaned_keywords:
        return 0.0
    hits = sum(1 for kw in cleaned_keywords if kw and kw in normalized_text)
    return round(hits / len(cleaned_keywords), 4)


def is_abstained_answer(answer: str) -> bool:
    normalized = normalize_match_text(answer)
    if not normalized:
        return True
    return any(normalize_match_text(marker) in normalized for marker in _ABSTAIN_MARKERS)


def citation_book_precision(citations: list[dict], gold_book_title: str) -> float:
    if not citations:
        return 0.0
    hits = sum(1 for citation in citations if citation.get("doc_title") == gold_book_title)
    return round(hits / len(citations), 4)


def citation_title_diversity(citations: list[dict]) -> float:
    if not citations:
        return 0.0
    titles = {
        str(citation.get("doc_title") or "").strip()
        for citation in citations
        if str(citation.get("doc_title") or "").strip()
    }
    return round(len(titles) / len(citations), 4)


def gold_chunk_rank(citations: list[dict], gold_chunk_id: str | None) -> int:
    target = str(gold_chunk_id or "").strip()
    if not target:
        return 0
    for idx, citation in enumerate(citations, 1):
        if str(citation.get("chunk_id") or "").strip() == target:
            return idx
    return 0


def _semantic_fact_match(answer: str, fact: str) -> bool:
    """判断 fact 是否在 answer 中被语义提及。"""
    norm_answer = normalize_match_text(answer)
    norm_fact = normalize_match_text(fact)
    if not norm_fact:
        return False
    # 直接子串匹配
    if norm_fact in norm_answer:
        return True
    # 关键词重叠：fact 中 >= 60% 的中文字符在 answer 中出现
    fact_chars = [c for c in norm_fact if "\u4e00" <= c <= "\u9fff"]
    if len(fact_chars) <= 2:
        return norm_fact in norm_answer
    hit_chars = sum(1 for c in fact_chars if c in norm_answer)
    return hit_chars / len(fact_chars) >= 0.6


def evaluate_item(item: dict, result: dict, judge_result: dict | None = None) -> dict[str, Any]:
    answer = result.get("answer", "")
    citations = result.get("citations", []) or []
    done = result.get("done", {}) or {}
    error = result.get("error", {}) or {}

    gold_book_title = item.get("gold_book_title", "")
    gold_chunk_text = item.get("gold_chunk_text", "")
    gold_chunk_id = item.get("gold_chunk_id") or ""
    reference_answer = item.get("reference_answer", "")
    keywords = item.get("keywords") or []
    matched_keywords = item.get("matched_keywords") or item.get("keywords") or []
    supported_facts = item.get("supported_facts") or []

    # ── 检索侧 ──
    citation_book_hit = any(c.get("doc_title") == gold_book_title for c in citations)
    exact_chunk_rank = gold_chunk_rank(citations, gold_chunk_id)
    evidence_scores = [evidence_overlap_score(c.get("text", ""), gold_chunk_text) for c in citations]
    max_evidence_score = max(evidence_scores, default=0.0)
    citation_text = "\n".join(
        f"{c.get('doc_title', '')}\n{c.get('text', '')}" for c in citations
    )
    abstained = is_abstained_answer(answer)

    # ── 生成侧 ──

    # ── 事实覆盖 ──
    if supported_facts:
        covered = sum(1 for f in supported_facts if _semantic_fact_match(answer, f))
        fact_coverage = round(covered / len(supported_facts), 4)
    else:
        fact_coverage = 0.0

    # ── LLM Judge ──
    faithful_score = 0
    hallucination_score = 0.0
    caution_score = 0
    if judge_result:
        faithful_score = judge_result.get("faithful_score", 0)
        hallucination_score = float(judge_result.get("hallucination_score", 0.0))
        fact_coverage_llm = float(judge_result.get("fact_coverage", fact_coverage))
        # 用 LLM 判断的事实覆盖覆盖 keyword 匹配的结果
        fact_coverage = round(max(fact_coverage, fact_coverage_llm), 4)
        caution_score = judge_result.get("caution_score", 0)

    return {
        "success": bool(answer) and not error,
        "error": error or None,
        "answer_length": len(answer),
        "citation_count": len(citations),
        "citation_rate": 1 if citations else 0,
        "citation_book_hit": 1 if citation_book_hit else 0,
        "citation_book_precision": citation_book_precision(citations, gold_book_title),
        "citation_title_diversity": citation_title_diversity(citations),
        "citation_evidence_hit": 1 if max_evidence_score >= 0.6 else 0,
        "citation_evidence_score": round(max_evidence_score, 4),
        "gold_chunk_hit": 1 if exact_chunk_rank > 0 else 0,
        "gold_chunk_rr": round(1.0 / exact_chunk_rank, 4) if exact_chunk_rank > 0 else 0.0,
        "keyword_hit_rate": keyword_hit_rate(answer, keywords),
        "matched_keywords_count": len(matched_keywords),
        "matched_keywords_hit_rate": keyword_hit_rate(answer, matched_keywords),
        "citation_keyword_hit_rate": keyword_hit_rate(citation_text, matched_keywords),
        "answer_abstained": 1 if abstained else 0,
        "abstain_with_gold_hit": 1 if abstained and exact_chunk_rank > 0 else 0,
        "fact_coverage": fact_coverage,
        "faithful_score": faithful_score,
        "hallucination_score": hallucination_score,
        "caution_score": caution_score,
        "latency_ms": int(done.get("latency_ms", 0) or 0),
        "total_tokens": int(done.get("total_tokens", 0) or 0),
    }


# ── summary ─────────────────────────────────────────────────

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


def build_summary(rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    total = len(rows)
    successes = [r for r in rows if r["metrics"]["success"]]
    latencies = [r["metrics"]["latency_ms"] for r in successes if r["metrics"]["latency_ms"] > 0]
    tokens = [r["metrics"]["total_tokens"] for r in successes if r["metrics"]["total_tokens"] > 0]

    def mean_metric(name: str) -> float:
        vals = [r["metrics"].get(name, 0) for r in rows]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    by_type: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[r.get("question_type", "unknown")].append(r)

    base_metrics = {
        "success_rate": "success",
        "citation_rate": "citation_rate",
        "book_hit_rate": "citation_book_hit",
        "book_precision": "citation_book_precision",
        "evidence_hit_rate": "citation_evidence_hit",
        "gold_chunk_hit_rate": "gold_chunk_hit",
        "avg_gold_chunk_rr": "gold_chunk_rr",
        "avg_keyword_hit_rate": "keyword_hit_rate",
        "avg_matched_keywords_hit_rate": "matched_keywords_hit_rate",
        "avg_citation_keyword_hit_rate": "citation_keyword_hit_rate",
        "abstention_rate": "answer_abstained",
        "abstain_with_gold_hit_rate": "abstain_with_gold_hit",
    }
    llm_metrics = {
        "avg_fact_coverage": "fact_coverage",
        "avg_faithful_score": "faithful_score",
        "avg_hallucination_score": "hallucination_score",
        "avg_caution_score": "caution_score",
        "avg_citation_title_diversity": "citation_title_diversity",
    }

    for key, items in grouped.items():
        entry: dict[str, Any] = {"count": len(items)}
        for metric_name, field in base_metrics.items():
            entry[metric_name] = round(sum(it["metrics"].get(field, 0) for it in items) / len(items), 4)
        for metric_name, field in llm_metrics.items():
            vals = [it["metrics"].get(field, 0) for it in items]
            entry[metric_name] = round(sum(vals) / len(vals), 4) if vals else 0.0
        by_type[key] = entry

    def grouped_summary(group_field: str) -> dict[str, dict[str, Any]]:
        grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            key = str(row.get(group_field) or "unknown")
            grouped_rows[key].append(row)
        output: dict[str, dict[str, Any]] = {}
        metric_fields = {
            "success_rate": "success",
            "book_hit_rate": "citation_book_hit",
            "gold_chunk_hit_rate": "gold_chunk_hit",
            "avg_fact_coverage": "fact_coverage",
            "avg_faithful_score": "faithful_score",
            "abstention_rate": "answer_abstained",
        }
        for key, items in grouped_rows.items():
            output[key] = {"count": len(items)}
            for metric_name, field in metric_fields.items():
                output[key][metric_name] = round(
                    sum(item["metrics"].get(field, 0) for item in items) / len(items),
                    4,
                )
        return output

    error_counter = Counter()
    for r in rows:
        err = r["metrics"].get("error")
        if err:
            error_counter[json.dumps(err, ensure_ascii=False)] += 1

    # Bad cases: low faithful + low fact_coverage
    bad_cases = sorted(
        [r for r in rows if r["metrics"]["faithful_score"] <= 2 or r["metrics"]["fact_coverage"] < 0.01],
        key=lambda x: x["metrics"].get("fact_coverage", 0),
    )[:10]

    return {
        "dataset": args.dataset,
        "base_url": args.base_url,
        "concurrency": args.concurrency,
        "llm_judge_enabled": args.llm_judge,
        "total": total,
        "success_count": len(successes),
        "success_rate": round(len(successes) / total, 4) if total else 0.0,
        "citation_rate": mean_metric("citation_rate"),
        "book_hit_rate": mean_metric("citation_book_hit"),
        "book_precision": mean_metric("citation_book_precision"),
        "evidence_hit_rate": mean_metric("citation_evidence_hit"),
        "avg_evidence_score": mean_metric("citation_evidence_score"),
        "gold_chunk_hit_rate": mean_metric("gold_chunk_hit"),
        "avg_gold_chunk_rr": mean_metric("gold_chunk_rr"),
        "avg_keyword_hit_rate": mean_metric("keyword_hit_rate"),
        "avg_matched_keywords_hit_rate": mean_metric("matched_keywords_hit_rate"),
        "avg_citation_keyword_hit_rate": mean_metric("citation_keyword_hit_rate"),
        "abstention_rate": mean_metric("answer_abstained"),
        "abstain_with_gold_hit_rate": mean_metric("abstain_with_gold_hit"),
        "avg_fact_coverage": mean_metric("fact_coverage"),
        "avg_faithful_score": mean_metric("faithful_score"),
        "avg_hallucination_score": mean_metric("hallucination_score"),
        "avg_caution_score": mean_metric("caution_score"),
        "avg_citation_title_diversity": mean_metric("citation_title_diversity"),
        "avg_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": round(percentile(latencies, 0.95), 2) if latencies else 0.0,
        "avg_total_tokens": round(statistics.mean(tokens), 2) if tokens else 0.0,
        "by_question_type": by_type,
        "by_difficulty": grouped_summary("difficulty"),
        "by_scenario_type": grouped_summary("scenario_type"),
        "top_errors": error_counter.most_common(10),
        "bad_cases_top10": [
            {
                "eval_id": b["eval_id"],
                "question": b.get("question", "")[:80],
                "difficulty": b.get("difficulty"),
                "scenario_type": b.get("scenario_type"),
                "faithful_score": b["metrics"].get("faithful_score", 0),
                "fact_coverage": b["metrics"].get("fact_coverage", 0),
                "gold_chunk_hit": b["metrics"].get("gold_chunk_hit", 0),
                "abstained": b["metrics"].get("answer_abstained", 0),
                "gold_book": b.get("gold_book_title", ""),
            }
            for b in bad_cases
        ],
    }


# ── runner ──────────────────────────────────────────────────

def build_authenticated_client(base_url: str, timeout: float, access_token: str | None = None) -> EvalClient:
    session = requests.Session()
    client = EvalClient(base_url=base_url, timeout=timeout, session=session)
    if access_token:
        client.set_token(access_token)
    return client


def run_one_eval_sync(
    item: dict[str, Any],
    *,
    base_url: str,
    timeout: float,
    access_token: str,
    case_profile_id: int,
    username: str,
    password: str,
    email: str,
    profile_name: str,
    llm_judge: bool = False,
    judge_model: str = "qwen-plus",
) -> dict[str, Any]:
    eval_id = item.get("eval_id") or f"eval-{uuid.uuid4().hex[:8]}"
    started_at = time.time()
    current_token = access_token
    current_case_profile_id = case_profile_id
    last_exc: Exception | None = None

    for attempt in range(2):
        client = build_authenticated_client(base_url, timeout, current_token)
        try:
            session_id = create_session(client, current_case_profile_id, title=f"Eval {eval_id}")
            sse_result = stream_chat(client, session_id, item["question"])

            # Run LLM judge if enabled
            judge_result = None
            if llm_judge and sse_result.get("answer"):
                judge_result = run_llm_judge(
                    question=item.get("question", ""),
                    reference_answer=item.get("reference_answer", ""),
                    gold_chunk_text=item.get("gold_chunk_text", ""),
                    answer=sse_result["answer"],
                    citations=sse_result.get("citations", []),
                    supported_facts=item.get("supported_facts", []),
                    base_url=base_url,
                    timeout=timeout,
                    model=judge_model,
                    access_token=current_token,
                )

            metrics = evaluate_item(item, sse_result, judge_result)
            return {
                "eval_id": eval_id,
                "question": item.get("question", ""),
                "reference_answer": item.get("reference_answer", ""),
                "question_type": item.get("question_type", item.get("bucket", "unknown")),
                "difficulty": item.get("difficulty"),
                "scenario_type": item.get("scenario_type"),
                "gold_book_title": item.get("gold_book_title"),
                "gold_chunk_index": item.get("gold_chunk_index"),
                "answer": sse_result["answer"],
                "citations": sse_result["citations"],
                "done": sse_result["done"],
                "llm_judge": judge_result,
                "metrics": metrics,
                "elapsed_wall_ms": int((time.time() - started_at) * 1000),
            }
        except Exception as exc:
            last_exc = exc
            if attempt == 0 and "401" in str(exc) and ("无效的令牌" in str(exc) or "invalid token" in str(exc).lower()):
                refresh_client = build_authenticated_client(base_url, timeout)
                try:
                    login_or_register(refresh_client, username, password, email)
                    current_case_profile_id = ensure_case_profile(refresh_client, profile_name)
                    if not refresh_client.access_token:
                        raise RuntimeError("重新登录后未获取到 access token")
                    current_token = refresh_client.access_token
                    continue
                finally:
                    refresh_client.session.close()
            break
        finally:
            client.session.close()

    return {
        "eval_id": eval_id,
        "question": item.get("question", ""),
        "reference_answer": item.get("reference_answer", ""),
        "question_type": item.get("question_type", item.get("bucket", "unknown")),
        "difficulty": item.get("difficulty"),
        "scenario_type": item.get("scenario_type"),
        "gold_book_title": item.get("gold_book_title"),
        "gold_chunk_index": item.get("gold_chunk_index"),
        "answer": "",
        "citations": [],
        "done": {},
        "llm_judge": None,
        "metrics": {
            "success": False,
            "error": {"message": str(last_exc) if last_exc else "unknown error"},
            "answer_length": 0,
            "citation_count": 0,
            "citation_rate": 0,
            "citation_book_hit": 0,
            "citation_book_precision": 0.0,
            "citation_title_diversity": 0.0,
            "citation_evidence_hit": 0,
            "citation_evidence_score": 0.0,
            "gold_chunk_hit": 0,
            "gold_chunk_rr": 0.0,
            "keyword_hit_rate": 0.0,
            "matched_keywords_count": len(item.get("matched_keywords") or item.get("keywords") or []),
            "matched_keywords_hit_rate": 0.0,
            "citation_keyword_hit_rate": 0.0,
            "answer_abstained": 0,
            "abstain_with_gold_hit": 0,
            "fact_coverage": 0.0,
            "faithful_score": 0,
            "hallucination_score": 0.0,
            "caution_score": 0,
            "latency_ms": 0,
            "total_tokens": 0,
        },
        "elapsed_wall_ms": int((time.time() - started_at) * 1000),
    }


async def main_async() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset).expanduser().resolve()
    results_path = Path(args.results).expanduser().resolve()
    summary_path = Path(args.summary).expanduser().resolve()

    rows = load_dataset(dataset_path, limit=args.limit)
    done_ids = load_done_ids(results_path) if args.resume else set()

    bootstrap_client = build_authenticated_client(args.base_url, args.timeout)
    login_or_register(bootstrap_client, args.username, args.password, args.email)
    case_profile_id = ensure_case_profile(bootstrap_client, args.profile_name)
    access_token = bootstrap_client.access_token
    bootstrap_client.session.close()
    if not access_token:
        raise RuntimeError("未获取到 access token")

    results_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.resume and results_path.exists() else "w"
    collected_rows: list[dict[str, Any]] = []

    if args.resume and results_path.exists():
        with results_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    collected_rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    pending_rows: list[dict[str, Any]] = []
    for idx, item in enumerate(rows, start=1):
        eval_id = item.get("eval_id") or f"eval-{idx:03d}"
        if eval_id in done_ids:
            continue
        pending_rows.append(item)

    semaphore = asyncio.Semaphore(max(1, args.concurrency))

    async def _worker(item: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            row = await asyncio.to_thread(
                run_one_eval_sync,
                item,
                base_url=args.base_url,
                timeout=args.timeout,
                access_token=access_token,
                case_profile_id=case_profile_id,
                username=args.username,
                password=args.password,
                email=args.email,
                profile_name=args.profile_name,
                llm_judge=args.llm_judge,
                judge_model=args.judge_model,
            )
            await asyncio.sleep(args.sleep)
            return row

    tasks = [asyncio.create_task(_worker(item)) for item in pending_rows]

    with results_path.open(mode, encoding="utf-8") as fout:
        for finished in asyncio.as_completed(tasks):
            row = await finished
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            fout.flush()
            collected_rows.append(row)

            m = row["metrics"]
            judge_str = ""
            if m.get("faithful_score"):
                judge_str = f" faithful={m['faithful_score']} halluc={m['hallucination_score']}"
            print(
                f"[{len(collected_rows):03d}] {row['eval_id']} "
                f"success={m['success']} "
                f"book_hit={m['citation_book_hit']} "
                f"evidence_hit={m['citation_evidence_hit']} "
                f"fact_cov={m['fact_coverage']:.2f} "
                f"faith={m['faithful_score']} "
                f"hallu={m['hallucination_score']:.2f} "
                f"kw_hit={m['matched_keywords_hit_rate']:.2f}{judge_str}"
            )

    summary = build_summary(collected_rows, args)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
