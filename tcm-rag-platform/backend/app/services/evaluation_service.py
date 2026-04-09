"""评测业务逻辑。"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, EvalDataError, EvalError, ResourceNotFoundError
from app.models.eval_task import EvalStatus, EvalTask


class EvaluationService:
    """评测服务。"""

    _allowed_types = {"retrieval", "generation", "rewrite", "full"}

    async def create_eval_task(
        self,
        db: AsyncSession,
        eval_type: str,
        dataset_path: str | None = None,
        triggered_by: int | None = None,
    ) -> EvalTask:
        if eval_type not in self._allowed_types:
            raise BadRequestError(
                message=f"无效的评测类型，允许值: {', '.join(self._allowed_types)}"
            )
        task = EvalTask(
            task_type=eval_type,
            status=EvalStatus.PENDING,
            config_json={"dataset_path": dataset_path} if dataset_path else None,
            triggered_by=triggered_by,
        )
        db.add(task)
        await db.flush()
        await db.refresh(task)
        return task

    async def run_evaluation(self, db: AsyncSession, task_id: int) -> EvalTask:
        task = await self._get_task_or_raise(db, task_id)
        task.status = EvalStatus.RUNNING
        task.started_at = datetime.utcnow()
        await db.flush()

        try:
            dataset = self._load_dataset(task.config_json)
            metrics = self._compute_metrics(task.task_type, dataset)
            task.result_json = metrics
            task.status = EvalStatus.COMPLETED
            task.completed_at = datetime.utcnow()
        except Exception as exc:
            task.status = EvalStatus.FAILED
            task.result_json = {"error": str(exc)}
            task.completed_at = datetime.utcnow()
            raise EvalError(message=f"评测执行失败: {exc}") from exc
        finally:
            await db.flush()
            await db.refresh(task)

        return task

    async def get_eval_results(self, db: AsyncSession, task_id: int) -> dict:
        task = await self._get_task_or_raise(db, task_id)
        return {
            "id": task.id,
            "task_id": task.task_id,
            "task_type": task.task_type,
            "status": task.status.value if hasattr(task.status, "value") else task.status,
            "config_json": task.config_json,
            "result_json": task.result_json,
            "triggered_by": task.triggered_by,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }

    async def list_eval_tasks(
        self,
        db: AsyncSession,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[EvalTask], int]:
        from sqlalchemy import func

        count_stmt = select(func.count()).select_from(EvalTask)
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = (
            select(EvalTask)
            .order_by(EvalTask.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items = list((await db.execute(stmt)).scalars().all())
        return items, total

    async def compare_eval_runs(
        self, db: AsyncSession, task_id_1: int, task_id_2: int
    ) -> dict:
        task1 = await self._get_task_or_raise(db, task_id_1)
        task2 = await self._get_task_or_raise(db, task_id_2)

        metrics1 = task1.result_json or {}
        metrics2 = task2.result_json or {}

        all_keys = set(list(metrics1.keys()) + list(metrics2.keys()))
        diff: dict[str, dict] = {}
        for key in all_keys:
            v1 = metrics1.get(key)
            v2 = metrics2.get(key)
            if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                diff[key] = {"task_1": v1, "task_2": v2, "delta": round(v2 - v1, 6)}
            else:
                diff[key] = {"task_1": v1, "task_2": v2}

        return {"task_1_id": task_id_1, "task_2_id": task_id_2, "diff": diff}

    # ── private helpers ─────────────────────────────────────

    async def _get_task_or_raise(self, db: AsyncSession, task_id: int) -> EvalTask:
        stmt = select(EvalTask).where(EvalTask.id == task_id)
        task = (await db.execute(stmt)).scalar_one_or_none()
        if task is None:
            raise ResourceNotFoundError(message="评测任务不存在")
        return task

    @staticmethod
    def _load_dataset(config_json: dict | None) -> list[dict]:
        if not config_json or not config_json.get("dataset_path"):
            return []
        path = Path(config_json["dataset_path"])
        if not path.exists():
            raise EvalDataError(message=f"数据集文件不存在: {path}")
        dataset: list[dict] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    dataset.append(json.loads(line))
        return dataset

    @staticmethod
    def _compute_metrics(eval_type: str, dataset: list[dict]) -> dict:
        """Compute evaluation metrics based on type and dataset."""
        if not dataset:
            return {"note": "无数据集，跳过指标计算"}

        if eval_type in ("retrieval", "full"):
            return EvaluationService._retrieval_metrics(dataset)
        elif eval_type == "generation":
            return EvaluationService._generation_metrics(dataset)
        elif eval_type == "rewrite":
            return EvaluationService._rewrite_metrics(dataset)
        return {}

    @staticmethod
    def _retrieval_metrics(dataset: list[dict]) -> dict:
        recall_5_list: list[float] = []
        recall_10_list: list[float] = []
        mrr_list: list[float] = []
        ndcg_list: list[float] = []

        for item in dataset:
            relevant = set(item.get("relevant_ids", []))
            retrieved = item.get("retrieved_ids", [])
            if not relevant:
                continue

            # Recall@K
            top5 = set(retrieved[:5])
            top10 = set(retrieved[:10])
            recall_5_list.append(len(relevant & top5) / len(relevant))
            recall_10_list.append(len(relevant & top10) / len(relevant))

            # MRR
            rr = 0.0
            for rank, rid in enumerate(retrieved, 1):
                if rid in relevant:
                    rr = 1.0 / rank
                    break
            mrr_list.append(rr)

            # NDCG@10
            dcg = 0.0
            for rank, rid in enumerate(retrieved[:10], 1):
                if rid in relevant:
                    dcg += 1.0 / math.log2(rank + 1)
            ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), 10)))
            ndcg_list.append(dcg / ideal if ideal > 0 else 0.0)

        def _avg(lst: list[float]) -> float:
            return round(sum(lst) / len(lst), 4) if lst else 0.0

        return {
            "recall@5": _avg(recall_5_list),
            "recall@10": _avg(recall_10_list),
            "mrr": _avg(mrr_list),
            "ndcg@10": _avg(ndcg_list),
            "sample_count": len(dataset),
        }

    @staticmethod
    def _generation_metrics(dataset: list[dict]) -> dict:
        faithfulness_scores: list[float] = []
        citation_precisions: list[float] = []
        citation_coverages: list[float] = []

        for item in dataset:
            if "faithfulness" in item:
                faithfulness_scores.append(float(item["faithfulness"]))
            cited = set(item.get("cited_ids", []))
            relevant = set(item.get("relevant_ids", []))
            if cited:
                citation_precisions.append(
                    len(cited & relevant) / len(cited) if relevant else 0.0
                )
            if relevant:
                citation_coverages.append(len(cited & relevant) / len(relevant))

        def _avg(lst: list[float]) -> float:
            return round(sum(lst) / len(lst), 4) if lst else 0.0

        return {
            "faithfulness": _avg(faithfulness_scores),
            "citation_precision": _avg(citation_precisions),
            "citation_coverage": _avg(citation_coverages),
            "sample_count": len(dataset),
        }

    @staticmethod
    def _rewrite_metrics(dataset: list[dict]) -> dict:
        scores: list[float] = []
        for item in dataset:
            if "score" in item:
                scores.append(float(item["score"]))

        def _avg(lst: list[float]) -> float:
            return round(sum(lst) / len(lst), 4) if lst else 0.0

        return {
            "avg_score": _avg(scores),
            "sample_count": len(dataset),
        }


evaluation_service = EvaluationService()
