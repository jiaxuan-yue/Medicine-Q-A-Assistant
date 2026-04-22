from types import SimpleNamespace

from app.services.portrait_memory_service import portrait_memory_service


def test_build_long_term_profile_from_flat_fields():
    stored_payload = portrait_memory_service.normalize_long_term_profile_payload(
        {
            "constitution_primary": "气虚",
            "constitution_secondary": ["阳虚"],
            "constitution_pinghe_score": 18,
            "constitution_qixu_score": 72,
            "constitution_yangxu_score": 65,
            "chronic_symptoms": ["乏力", "容易感冒"],
            "dietary_restrictions": ["少生冷", "少辛辣"],
            "constitution_assessed_at": "2026-04-01",
            "tongue_color": "舌淡红",
            "tongue_coating": "薄白",
            "tongue_constitution_hint": "气虚体质倾向",
        },
        allergy_history="花粉过敏",
    )
    profile = portrait_memory_service.build_long_term_profile(
        SimpleNamespace(
            **stored_payload,
            allergy_history="花粉过敏",
            medical_history=None,
        )
    )

    assert profile["primary_constitution"] == "气虚"
    assert profile["secondary_constitutions"] == ["阳虚"]
    assert profile["scores"]["气虚"] == 72
    assert profile["scores"]["痰湿"] == 0
    assert profile["allergy_history"] == ["花粉过敏"]
    assert profile["chronic_symptoms"] == ["乏力", "容易感冒"]
    assert profile["dietary_restrictions"] == ["少生冷", "少辛辣"]
    assert profile["tongue_coating"] == "薄白"


def test_update_session_syndrome_memory_marks_resolution_and_keeps_recent_limit():
    seeded = portrait_memory_service.update_session_syndrome_memory(
        syndrome_memory=[],
        latest_query="我上周感冒了，怕冷咳嗽三天",
        answer_style="consult",
        consultation_context={
            "primary_symptom": "感冒",
            "duration": "三天",
            "accompanying_symptoms": "怕冷、咳嗽",
        },
        source_message_id="m1",
    )

    assert seeded
    assert seeded[0]["status"] == "active"
    assert "avoid_tonifying_until_resolved" in seeded[0]["risk_tags"]

    resolved = portrait_memory_service.update_session_syndrome_memory(
        syndrome_memory=seeded,
        latest_query="现在已经好了，不咳了，想补一补",
        answer_style="dietary",
        consultation_context={"recovery_status": "已恢复"},
        source_message_id="m2",
    )

    assert resolved[0]["status"] == "resolved"
    assert resolved[0]["resolved_at"] is not None


def test_build_recovery_followup_for_recent_unresolved_acute_memory():
    syndrome_memory = portrait_memory_service.update_session_syndrome_memory(
        syndrome_memory=[],
        latest_query="这两天感冒了，怕冷咽痛",
        answer_style="consult",
        consultation_context={
            "primary_symptom": "感冒",
            "accompanying_symptoms": "怕冷、咽痛",
            "duration": "两天",
        },
        source_message_id="m1",
    )

    followup = portrait_memory_service.build_recovery_followup(
        query="现在想补身体，炖点补汤行吗",
        syndrome_memory=syndrome_memory,
    )

    assert followup is not None
    assert "完全恢复" in followup["question"]


def test_retrieve_relevant_short_term_memories_prefers_recent_active_risk():
    syndrome_memory = portrait_memory_service.update_session_syndrome_memory(
        syndrome_memory=[],
        latest_query="我最近感冒，怕冷咳嗽",
        answer_style="consult",
        consultation_context={
            "primary_symptom": "感冒",
            "accompanying_symptoms": "怕冷、咳嗽",
        },
        source_message_id="m1",
    )
    syndrome_memory = portrait_memory_service.update_session_syndrome_memory(
        syndrome_memory=syndrome_memory,
        latest_query="另外前阵子胃口差，但现在好多了",
        answer_style="consult",
        consultation_context={
            "primary_symptom": "胃口差",
        },
        source_message_id="m2",
    )

    ranked = portrait_memory_service.retrieve_relevant_short_term_memories(
        query="我现在想补身体",
        syndrome_memory=syndrome_memory,
    )

    assert ranked
    assert ranked[0]["summary"].startswith("主症状：感冒")
    assert ranked[0]["status"] == "active"
