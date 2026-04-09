"""BadCase 业务逻辑。"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import Feedback, FeedbackType

# 标准 bad-case 分类
BADCASE_CATEGORIES = [
    "rewrite_error",
    "retrieval_miss",
    "rerank_error",
    "graph_error",
    "citation_error",
    "hallucination",
    "safety_missing",
    "other",
]


class BadCaseService:
    """BadCase 服务 — 基于 Feedback(type=badcase) 的子集。"""

    async def list_badcases(
        self,
        db: AsyncSession,
        category: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Feedback], int]:
        base = select(Feedback).where(Feedback.feedback_type == FeedbackType.BADCASE)
        count_base = (
            select(func.count())
            .select_from(Feedback)
            .where(Feedback.feedback_type == FeedbackType.BADCASE)
        )

        if category:
            # category 存储在 metadata_json -> "category"
            base = base.where(
                Feedback.metadata_json["category"].as_string() == category
            )
            count_base = count_base.where(
                Feedback.metadata_json["category"].as_string() == category
            )

        total = (await db.execute(count_base)).scalar() or 0
        stmt = base.order_by(Feedback.created_at.desc()).offset((page - 1) * size).limit(size)
        items = list((await db.execute(stmt)).scalars().all())
        return items, total

    async def get_badcase_stats(self, db: AsyncSession) -> dict:
        """按 category 统计 bad-case 数量 + 7 天趋势。"""
        # counts by category using metadata_json
        stmt = (
            select(
                Feedback.metadata_json["category"].as_string().label("cat"),
                func.count().label("cnt"),
            )
            .where(Feedback.feedback_type == FeedbackType.BADCASE)
            .group_by(Feedback.metadata_json["category"].as_string())
        )
        rows = (await db.execute(stmt)).all()
        by_category: dict[str, int] = {}
        total = 0
        for cat, cnt in rows:
            by_category[cat or "uncategorized"] = cnt
            total += cnt

        # 7-day trend
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        trend_stmt = (
            select(
                func.date(Feedback.created_at).label("day"),
                func.count().label("count"),
            )
            .where(Feedback.feedback_type == FeedbackType.BADCASE)
            .where(Feedback.created_at >= seven_days_ago)
            .group_by(func.date(Feedback.created_at))
            .order_by(func.date(Feedback.created_at))
        )
        trend_rows = (await db.execute(trend_stmt)).all()
        trend = [{"date": str(r.day), "count": r.count} for r in trend_rows]

        return {"total": total, "by_category": by_category, "trend": trend}

    @staticmethod
    def categorize_badcase(content: str | None) -> str:
        """根据反馈内容自动归类 bad-case 类别（简单关键词匹配）。"""
        if not content:
            return "other"
        text = content.lower()
        keyword_map = {
            "rewrite_error": ["改写", "rewrite", "query rewrite", "查询改写"],
            "retrieval_miss": ["检索", "retrieval", "召回", "未找到", "miss"],
            "rerank_error": ["排序", "rerank", "重排"],
            "graph_error": ["图谱", "graph", "知识图谱", "实体"],
            "citation_error": ["引用", "citation", "出处", "来源错误"],
            "hallucination": ["幻觉", "hallucination", "编造", "虚构", "不真实"],
            "safety_missing": ["安全", "safety", "禁忌", "注意事项", "副作用"],
        }
        for category, keywords in keyword_map.items():
            for kw in keywords:
                if kw in text:
                    return category
        return "other"


badcase_service = BadCaseService()
