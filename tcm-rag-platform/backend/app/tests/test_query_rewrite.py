from app.services.query_rewrite_service import rewrite_query


def test_query_rewrite_extracts_entities_and_intent():
    result = rewrite_query("最近总睡不好，还口苦烦躁")
    assert "失眠" in result.entities
    assert "口苦" in result.entities
    assert result.intent == "symptom_diagnosis"
    assert any("中医辨证" in item for item in result.rewrite_queries)
