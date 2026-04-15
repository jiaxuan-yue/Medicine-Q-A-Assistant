#!/usr/bin/env python3
"""Run grounded eval dataset against the live backend and compute summary metrics.

Features:
- login/register eval user automatically
- ensure one complete case profile exists
- create a fresh chat session per sample
- call the current `/api/v1/chats/{session_id}/stream` endpoint
- parse SSE events
- save per-sample results and aggregate metrics
- run requests concurrently via asyncio + thread workers
"""

from __future__ import annotations

import argparse
import asyncio
import json
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
DEFAULT_RESULTS = PROJECT_ROOT / "data" / "eval" / "grounded_eval_results.jsonl"
DEFAULT_SUMMARY = PROJECT_ROOT / "data" / "eval" / "grounded_eval_summary.json"


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
    parser = argparse.ArgumentParser(description="批量跑 grounded eval 数据集并输出检索/生成指标")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端基地址，默认 http://127.0.0.1:8000")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="评测数据集 jsonl 路径")
    parser.add_argument("--results", default=str(DEFAULT_RESULTS), help="逐条评测结果 jsonl 输出路径")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY), help="汇总 summary json 输出路径")
    parser.add_argument("--username", default="eval_runner", help="评测账号用户名")
    parser.add_argument("--password", default="EvalRunner123", help="评测账号密码")
    parser.add_argument("--email", default="eval_runner@tcm.local", help="评测账号邮箱")
    parser.add_argument("--profile-name", default="评测角色", help="自动创建/复用的角色名称")
    parser.add_argument("--limit", type=int, help="只评前 N 条")
    parser.add_argument("--timeout", type=float, default=120.0, help="单次 HTTP 请求超时秒数")
    parser.add_argument("--sleep", type=float, default=0.1, help="每条请求之间的 sleep 秒数")
    parser.add_argument("--concurrency", type=int, default=4, help="并发评测数，默认 4")
    parser.add_argument("--resume", action="store_true", help="若结果文件已存在，则跳过已完成 eval_id")
    return parser.parse_args()


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
    except Exception as exc:  # noqa: BLE001
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
        "POST",
        "/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    if register_response.status_code == 200:
        client.set_token(ensure_ok(register_response)["data"]["access_token"])
        return

    raise RuntimeError(
        f"登录/注册均失败。\nlogin={login_response.status_code} {login_response.text[:300]}\n"
        f"register={register_response.status_code} {register_response.text[:300]}"
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
        client.request(
            "POST",
            "/chats",
            json={"title": title, "case_profile_id": case_profile_id},
        )
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
        "POST",
        f"/chats/{session_id}/stream",
        json={"query": query},
        stream=True,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"流式问答失败: {response.status_code} {response.text[:300]}")
    return parse_sse_response(response)


def is_invalid_token_error(exc: Exception) -> bool:
    text = str(exc)
    lowered = text.lower()
    return "401" in text and ("无效的令牌" in text or "invalid token" in lowered)


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


def rouge_l_f1(pred: str, ref: str) -> float:
    a = tokenize(pred)
    b = tokenize(ref)
    if not a or not b:
        return 0.0
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs = dp[-1][-1]
    precision = lcs / len(a)
    recall = lcs / len(b)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


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
    cleaned_keywords = [normalize_match_text(keyword) for keyword in (keywords or []) if str(keyword).strip()]
    if not cleaned_keywords:
        return 0.0
    hits = sum(1 for keyword in cleaned_keywords if keyword and keyword in normalized_text)
    return round(hits / len(cleaned_keywords), 4)


def evaluate_item(item: dict, result: dict) -> dict[str, Any]:
    answer = result.get("answer", "")
    citations = result.get("citations", []) or []
    done = result.get("done", {}) or {}
    error = result.get("error", {}) or {}

    gold_book_title = item.get("gold_book_title", "")
    gold_chunk_text = item.get("gold_chunk_text", "")
    reference_answer = item.get("reference_answer", "")
    matched_keywords = item.get("matched_keywords") or []

    citation_book_hit = any(c.get("doc_title") == gold_book_title for c in citations)
    evidence_scores = [evidence_overlap_score(c.get("text", ""), gold_chunk_text) for c in citations]
    max_evidence_score = max(evidence_scores, default=0.0)
    citation_text = "\n".join(
        f"{citation.get('doc_title', '')}\n{citation.get('text', '')}"
        for citation in citations
    )

    return {
        "success": bool(answer) and not error,
        "error": error or None,
        "answer_length": len(answer),
        "citation_count": len(citations),
        "citation_rate": 1 if citations else 0,
        "citation_book_hit": 1 if citation_book_hit else 0,
        "citation_evidence_hit": 1 if max_evidence_score >= 0.6 else 0,
        "citation_evidence_score": round(max_evidence_score, 4),
        "answer_rouge_l_f1": round(rouge_l_f1(answer, reference_answer), 4),
        "matched_keywords_count": len(matched_keywords),
        "matched_keywords_hit_rate": keyword_hit_rate(answer, matched_keywords),
        "citation_keyword_hit_rate": keyword_hit_rate(citation_text, matched_keywords),
        "latency_ms": int(done.get("latency_ms", 0) or 0),
        "total_tokens": int(done.get("total_tokens", 0) or 0),
    }


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
    successes = [row for row in rows if row["metrics"]["success"]]
    latencies = [row["metrics"]["latency_ms"] for row in successes if row["metrics"]["latency_ms"] > 0]
    tokens = [row["metrics"]["total_tokens"] for row in successes if row["metrics"]["total_tokens"] > 0]

    def mean_metric(name: str) -> float:
        vals = [row["metrics"][name] for row in rows]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    by_type: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("question_type", "unknown")].append(row)

    for key, items in grouped.items():
        by_type[key] = {
            "count": len(items),
            "success_rate": round(sum(item["metrics"]["success"] for item in items) / len(items), 4),
            "citation_rate": round(sum(item["metrics"]["citation_rate"] for item in items) / len(items), 4),
            "book_hit_rate": round(sum(item["metrics"]["citation_book_hit"] for item in items) / len(items), 4),
            "evidence_hit_rate": round(sum(item["metrics"]["citation_evidence_hit"] for item in items) / len(items), 4),
            "avg_rouge_l_f1": round(sum(item["metrics"]["answer_rouge_l_f1"] for item in items) / len(items), 4),
            "avg_matched_keywords_hit_rate": round(sum(item["metrics"]["matched_keywords_hit_rate"] for item in items) / len(items), 4),
            "avg_citation_keyword_hit_rate": round(sum(item["metrics"]["citation_keyword_hit_rate"] for item in items) / len(items), 4),
        }

    error_counter = Counter()
    for row in rows:
        err = row["metrics"].get("error")
        if err:
            error_counter[json.dumps(err, ensure_ascii=False)] += 1

    return {
        "dataset": args.dataset,
        "base_url": args.base_url,
        "concurrency": args.concurrency,
        "total": total,
        "success_count": len(successes),
        "success_rate": round(len(successes) / total, 4) if total else 0.0,
        "avg_answer_rouge_l_f1": mean_metric("answer_rouge_l_f1"),
        "citation_rate": mean_metric("citation_rate"),
        "book_hit_rate": mean_metric("citation_book_hit"),
        "evidence_hit_rate": mean_metric("citation_evidence_hit"),
        "avg_evidence_score": mean_metric("citation_evidence_score"),
        "avg_matched_keywords_hit_rate": mean_metric("matched_keywords_hit_rate"),
        "avg_citation_keyword_hit_rate": mean_metric("citation_keyword_hit_rate"),
        "avg_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": round(percentile(latencies, 0.95), 2) if latencies else 0.0,
        "avg_total_tokens": round(statistics.mean(tokens), 2) if tokens else 0.0,
        "by_question_type": by_type,
        "top_errors": error_counter.most_common(10),
    }


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
            metrics = evaluate_item(item, sse_result)
            return {
                "eval_id": eval_id,
                "question": item.get("question", ""),
                "reference_answer": item.get("reference_answer", ""),
                "question_type": item.get("question_type", item.get("bucket", "unknown")),
                "difficulty": item.get("difficulty"),
                "gold_book_title": item.get("gold_book_title"),
                "gold_chunk_index": item.get("gold_chunk_index"),
                "answer": sse_result["answer"],
                "citations": sse_result["citations"],
                "done": sse_result["done"],
                "metrics": metrics,
                "elapsed_wall_ms": int((time.time() - started_at) * 1000),
            }
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == 0 and is_invalid_token_error(exc):
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
        "gold_book_title": item.get("gold_book_title"),
        "gold_chunk_index": item.get("gold_chunk_index"),
        "answer": "",
        "citations": [],
        "done": {},
        "metrics": {
            "success": False,
            "error": {"message": str(last_exc) if last_exc else "unknown error"},
            "answer_length": 0,
            "citation_count": 0,
            "citation_rate": 0,
            "citation_book_hit": 0,
            "citation_evidence_hit": 0,
            "citation_evidence_score": 0.0,
            "answer_rouge_l_f1": 0.0,
            "matched_keywords_count": len(item.get("matched_keywords") or []),
            "matched_keywords_hit_rate": 0.0,
            "citation_keyword_hit_rate": 0.0,
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

            print(
                f"[{len(collected_rows):03d}] {row['eval_id']} "
                f"success={row['metrics']['success']} "
                f"rouge_l={row['metrics']['answer_rouge_l_f1']:.4f} "
                f"book_hit={row['metrics']['citation_book_hit']} "
                f"evidence_hit={row['metrics']['citation_evidence_hit']}"
            )

    summary = build_summary(collected_rows, args)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
