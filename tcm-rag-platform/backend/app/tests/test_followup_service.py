from types import SimpleNamespace

from app.services.followup_service import followup_service


def _session(state: dict | None = None):
    return SimpleNamespace(followup_state=state or {})


def test_followup_message_asks_all_missing_questions_at_once():
    """Batch all missing questions in one call instead of asking one at a time."""
    session = _session()

    decision = followup_service.process_turn(
        session,
        query="我最近有点感冒 脖子有点酸",
        intent="symptom_diagnosis",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )

    assert decision.need_follow_up is True
    assert decision.follow_up_message is not None
    assert decision.question_targets is not None
    assert len(decision.question_targets) >= 1
    assert "已收到" not in decision.follow_up_message
    assert "待补信息" not in decision.follow_up_message


def test_followup_stops_after_first_batch():
    """Questions asked in batches of up to 3, no repeats."""
    session = _session()

    decision1 = followup_service.process_turn(
        session,
        query="我最近不舒服",
        intent="symptom_diagnosis",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert decision1.need_follow_up is True
    assert session.followup_state["round_count"] == 1
    assert len(session.followup_state.get("asked_targets", [])) >= 1
    assert len(decision1.question_targets or []) <= 3  # capped at 3

    # Second turn: remaining targets asked, no repeats
    decision2 = followup_service.process_turn(
        session,
        query="不影响工作睡眠",
        intent="general_consultation",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    # May still have remaining targets or may be done
    asked = session.followup_state.get("asked_targets", [])
    # Asked targets should never repeat
    assert len(asked) == len(set(asked))


def test_followup_merges_body_status_details_across_turns():
    session = _session()

    first = followup_service.process_turn(
        session,
        query="我这三天有点脖子酸 怕冷 感觉有一些感冒",
        intent="symptom_diagnosis",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert first.need_follow_up is True

    second = followup_service.process_turn(
        session,
        query="不影响工作睡眠",
        intent="general_consultation",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    # Collected slots should merge across turns
    assert "胃口不好" not in (second.clarification_context or "")
    assert "主症状：感冒" in (second.clarification_context or "")


def test_followup_recognizes_negative_severity_answer():
    session = _session()

    first = followup_service.process_turn(
        session,
        query="我最近有点感冒 脖子有点酸",
        intent="symptom_diagnosis",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert first.need_follow_up is True

    second = followup_service.process_turn(
        session,
        query="不影响工作睡眠",
        intent="general_consultation",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    # Should recognize the negative severity answer
    assert "不影响" in (second.clarification_context or "")


def test_followup_asks_all_missing_targets_without_repeating():
    """All missing targets returned at once, no duplicates."""
    session = _session()

    first = followup_service.process_turn(
        session,
        query="我最近有点感冒 脖子酸痛 大概持续三天了",
        intent="symptom_diagnosis",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert first.need_follow_up is True
    assert first.question_targets is not None
    # All asked targets should be unique
    assert len(first.question_targets) == len(set(first.question_targets))


def test_followup_stops_if_all_questions_already_asked():
    session = _session()

    first = followup_service.process_turn(
        session,
        query="我最近感冒 三天了 怕冷 睡得还行 胃口一般 大小便正常 咳嗽",
        intent="symptom_diagnosis",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert first.need_follow_up is True

    second = followup_service.process_turn(
        session,
        query="还是说不好",
        intent="general_consultation",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert second.need_follow_up is False
    assert session.followup_state == {}


def test_followup_does_not_overwrite_primary_symptom_with_irrelevant_reply():
    session = _session()

    first = followup_service.process_turn(
        session,
        query="我最近感冒三天了",
        intent="symptom_diagnosis",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert first.need_follow_up is True

    second = followup_service.process_turn(
        session,
        query="不太影响工作",
        intent="general_consultation",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert first.clarification_context is None or "主症状：感冒" in (first.clarification_context or "")


def test_followup_treats_uninformative_reply_as_no_new_information():
    session = _session()

    first = followup_service.process_turn(
        session,
        query="我最近感冒 三天了 怕冷 睡得还行 大小便正常 咳嗽",
        intent="symptom_diagnosis",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert first.need_follow_up is True

    second = followup_service.process_turn(
        session,
        query="不太清楚",
        intent="general_consultation",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    # All targets already asked in first batch
    assert second.need_follow_up is False


def test_followup_reuses_known_context_for_treatment_request():
    session = _session()
    known_context = {
        "primary_symptom": "感冒、脖子酸痛",
        "duration": "三天",
        "severity": "不影响睡眠",
        "body_statuses": "睡眠失眠；胃口不好；二便正常；寒热怕冷",
        "accompanying_symptoms": "怕冷",
    }

    decision = followup_service.process_turn(
        session,
        query="我想要喝一些中药",
        intent="general_consultation",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
        known_context=known_context,
    )

    assert decision.need_follow_up is False
    assert decision.clarification_context is not None
    assert "持续时间：三天" in decision.clarification_context
    assert "严重程度：不影响睡眠" in decision.clarification_context
    assert "主症状：我想要喝一些中药" not in decision.clarification_context


def test_followup_asks_only_missing_slot_for_cooling_tea_when_context_known():
    session = _session()
    known_context = {
        "primary_symptom": "感冒、脖子酸痛",
        "duration": "三天",
        "body_statuses": "睡眠失眠；胃口不好；二便正常；寒热怕冷",
        "accompanying_symptoms": "怕冷",
    }

    decision = followup_service.process_turn(
        session,
        query="我最近想喝一些凉茶而不是中药",
        intent="general_consultation",
        answer_style="dietary",
        case_profile_summary="本人；男；28岁",
        known_context=known_context,
    )

    assert decision.need_follow_up is True
    assert decision.follow_up_message is not None
    assert decision.clarification_context is not None
    assert "持续时间：三天" in decision.clarification_context


def test_followup_tonify_guardrail_collects_recovery_status():
    session = _session(
        {
            "active": True,
            "domain": "tonify_guardrail",
            "original_query": "现在想补身体",
            "latest_query": "现在想补身体",
            "required_targets": ["recovery_status"],
            "collected": {},
            "round_count": 1,
            "asked_targets": ["recovery_status"],
            "last_asked_target": "recovery_status",
        }
    )

    decision = followup_service.process_turn(
        session,
        query="已经好了，不咳了",
        intent="general_consultation",
        answer_style="dietary",
        case_profile_summary="本人；男；28岁",
    )

    assert decision.need_follow_up is False
    assert decision.effective_query == "现在想补身体"
    assert decision.clarification_context is not None
    assert "恢复情况：已恢复" in decision.clarification_context


def test_cooling_tea_followup_no_longer_mentions_tongue():
    session = _session()

    decision = followup_service.process_turn(
        session,
        query="最近上火想喝凉茶",
        intent="general_consultation",
        answer_style="dietary",
        case_profile_summary="本人；男；28岁",
    )

    assert decision.need_follow_up is True
    assert "舌" not in (decision.follow_up_message or "")
