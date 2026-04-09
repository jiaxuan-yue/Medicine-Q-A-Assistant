"""评测相关 schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EvalRunRequest(BaseModel):
    eval_type: str  # retrieval / generation / rewrite / full
    dataset_path: str | None = None


class EvalTaskOut(BaseModel):
    id: int
    task_id: str
    task_type: str
    status: str
    config_json: dict | None = None
    result_json: dict | None = None
    triggered_by: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EvalCompareRequest(BaseModel):
    task_id_1: int
    task_id_2: int


class EvalCompareOut(BaseModel):
    task_1: EvalTaskOut
    task_2: EvalTaskOut
    diff: dict
