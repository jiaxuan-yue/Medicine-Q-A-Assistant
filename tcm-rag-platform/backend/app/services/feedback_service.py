"""反馈业务逻辑。"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ResourceNotFoundError
from app.models.feedback import Feedback, FeedbackType
from app.schemas.feedback import FeedbackCreate


class FeedbackService:
    """反馈服务。"""

    _valid_types = {t.value for t in FeedbackType}

    async def create_feedback(
        self, db: AsyncSession, user_id: int, data: FeedbackCreate
    ) -> Feedback:
        if data.feedback_type not in self._valid_types:
            raise BadRequestError(
                message=f"无效的反馈类型，允许值: {', '.join(self._valid_types)}"
            )
        feedback = Feedback(
            message_id=data.message_id,
            user_id=user_id,
            feedback_type=FeedbackType(data.feedback_type),
            content=data.content,
            metadata_json=data.metadata_json,
        )
        db.add(feedback)
        await db.flush()
        await db.refresh(feedback)
        return feedback

    async def list_feedback(
        self,
        db: AsyncSession,
        user_id: int | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Feedback], int]:
        stmt = select(Feedback).order_by(Feedback.created_at.desc())
        count_stmt = select(func.count()).select_from(Feedback)

        if user_id is not None:
            stmt = stmt.where(Feedback.user_id == user_id)
            count_stmt = count_stmt.where(Feedback.user_id == user_id)

        total = (await db.execute(count_stmt)).scalar() or 0
        stmt = stmt.offset((page - 1) * size).limit(size)
        items = list((await db.execute(stmt)).scalars().all())
        return items, total

    async def get_feedback(self, db: AsyncSession, feedback_id: int) -> Feedback:
        stmt = select(Feedback).where(Feedback.id == feedback_id)
        result = (await db.execute(stmt)).scalar_one_or_none()
        if result is None:
            raise ResourceNotFoundError(message="反馈不存在")
        return result

    async def get_feedback_stats(self, db: AsyncSession) -> dict:
        # --- counts by type ---
        type_stmt = (
            select(Feedback.feedback_type, func.count())
            .group_by(Feedback.feedback_type)
        )
        rows = (await db.execute(type_stmt)).all()
        by_type: dict[str, int] = {}
        total = 0
        for ft, cnt in rows:
            key = ft.value if hasattr(ft, "value") else str(ft)
            by_type[key] = cnt
            total += cnt

        # --- 7-day trend ---
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        trend_stmt = (
            select(
                func.date(Feedback.created_at).label("day"),
                func.count().label("count"),
            )
            .where(Feedback.created_at >= seven_days_ago)
            .group_by(func.date(Feedback.created_at))
            .order_by(func.date(Feedback.created_at))
        )
        trend_rows = (await db.execute(trend_stmt)).all()
        trend = [{"date": str(row.day), "count": row.count} for row in trend_rows]

        return {"total": total, "by_type": by_type, "trend": trend}


feedback_service = FeedbackService()
