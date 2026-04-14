"""多角色基础档案 schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CaseProfileBase(BaseModel):
    profile_name: str
    gender: str | None = None
    age: int | None = None
    height_cm: int | None = None
    weight_kg: int | None = None
    medical_history: str | None = None
    allergy_history: str | None = None
    current_medications: str | None = None
    menstrual_history: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class CaseProfileCreate(CaseProfileBase):
    pass


class CaseProfileUpdate(CaseProfileBase):
    pass


class CaseProfileOut(CaseProfileBase):
    id: int
    user_id: int
    profile_completed: bool
    summary: str
    created_at: str | None = None
    updated_at: str | None = None
