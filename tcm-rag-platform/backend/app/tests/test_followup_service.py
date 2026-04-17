from types import SimpleNamespace

from app.services.followup_service import followup_service


def _session(state: dict | None = None):
    return SimpleNamespace(followup_state=state or {})


def test_followup_message_only_asks_one_question():
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
    assert decision.follow_up_message.startswith("第 1 问 / 共 3 问")
    assert "已收到" not in decision.follow_up_message
    assert "待补信息" not in decision.follow_up_message


def test_followup_stops_after_three_rounds():
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

    decision2 = followup_service.process_turn(
        session,
        query="不影响工作睡眠",
        intent="general_consultation",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert decision2.need_follow_up is True
    assert session.followup_state["round_count"] == 2

    decision3 = followup_service.process_turn(
        session,
        query="睡得一般 胃口差 大小便正常",
        intent="general_consultation",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert decision3.need_follow_up is True
    assert session.followup_state["round_count"] == 3

    decision4 = followup_service.process_turn(
        session,
        query="还有点怕冷乏力",
        intent="general_consultation",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert decision4.need_follow_up is False
    assert session.followup_state == {}


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
    assert second.need_follow_up is True

    third = followup_service.process_turn(
        session,
        query="怕冷 胃口不好 大小便正常",
        intent="general_consultation",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert third.need_follow_up is False
    assert third.clarification_context is not None
    assert "胃口不好" in third.clarification_context
    assert "二便正常" in third.clarification_context
    assert "主症状：感冒、脖子酸" in third.clarification_context


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
    assert second.need_follow_up is True
    assert second.clarification_context is not None
    assert "不影响" in second.clarification_context


def test_followup_moves_to_a_different_question_instead_of_repeating():
    session = _session()

    first = followup_service.process_turn(
        session,
        query="我最近有点感冒 脖子酸痛 大概持续三天了",
        intent="symptom_diagnosis",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert first.need_follow_up is True
    assert "现在大概有多严重" in (first.follow_up_message or "")

    second = followup_service.process_turn(
        session,
        query="不想输睡眠工作 食欲不是很好",
        intent="general_consultation",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert second.need_follow_up is True
    assert second.follow_up_message is not None
    assert "最近睡眠怎么样" in second.follow_up_message
    assert "现在大概有多严重" not in second.follow_up_message
    assert second.question_target == "body_status.sleep"


def test_followup_stops_if_only_repeated_question_remains():
    session = _session()

    first = followup_service.process_turn(
        session,
        query="我最近感冒 三天了 怕冷 睡得还行 胃口一般 大小便正常 咳嗽",
        intent="symptom_diagnosis",
        answer_style="consult",
        case_profile_summary="本人；男；28岁",
    )
    assert first.need_follow_up is True
    assert "现在大概有多严重" in (first.follow_up_message or "")

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
    assert second.clarification_context is not None
    assert "主症状：感冒" in second.clarification_context
    assert "主症状：不太影响工作" not in second.clarification_context


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
    assert second.need_follow_up is True
    assert second.follow_up_message is not None
    assert "最近胃口怎么样" in second.follow_up_message
    assert second.clarification_context is not None
    assert "主症状：不太清楚" not in second.clarification_context


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
    assert "有没有怕冷、腹泻、经期、怀孕/备孕/哺乳、慢病或正在用药" in decision.follow_up_message
    assert "这个情况大概持续多久了" not in decision.follow_up_message
    assert "再补一下整体状态" not in decision.follow_up_message
    assert decision.clarification_context is not None
    assert "持续时间：三天" in decision.clarification_context
