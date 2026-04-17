import asyncio
import sys
from types import SimpleNamespace

from app.services.followup_question_service import followup_question_service


def test_followup_question_service_uses_llm_output(monkeypatch):
    async def fake_chat(messages, model=None, temperature=0.7, top_p=0.9, max_tokens=2000):
        return "最近睡得怎么样？\n"

    monkeypatch.setitem(
        sys.modules,
        "app.integrations.llm_client",
        SimpleNamespace(llm_client=SimpleNamespace(chat=fake_chat)),
    )

    question = asyncio.run(
        followup_question_service.generate_question(
            domain="symptom",
            target="body_status.sleep",
            collected_slots={"primary_symptom": "感冒", "severity": "不严重"},
            latest_query="不严重 食欲一般",
            asked_targets=["severity"],
        )
    )

    assert question == "最近睡得怎么样？"


def test_followup_question_service_falls_back_when_llm_fails(monkeypatch):
    async def fake_chat(messages, model=None, temperature=0.7, top_p=0.9, max_tokens=2000):
        raise RuntimeError("boom")

    monkeypatch.setitem(
        sys.modules,
        "app.integrations.llm_client",
        SimpleNamespace(llm_client=SimpleNamespace(chat=fake_chat)),
    )

    question = asyncio.run(
        followup_question_service.generate_question(
            domain="symptom",
            target="body_status.bowel",
            collected_slots={"primary_symptom": "感冒"},
            latest_query="不太清楚",
            asked_targets=["severity", "body_status.sleep"],
        )
    )

    assert question == "最近二便怎么样，大便和小便基本正常吗？"
