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
    chronic_symptoms: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    constitution_primary: str | None = None
    constitution_secondary: list[str] = Field(default_factory=list)
    constitution_pinghe_score: int | None = None
    constitution_qixu_score: int | None = None
    constitution_yangxu_score: int | None = None
    constitution_yinxu_score: int | None = None
    constitution_tanshi_score: int | None = None
    constitution_shire_score: int | None = None
    constitution_xueyu_score: int | None = None
    constitution_qiyu_score: int | None = None
    constitution_tebing_score: int | None = None
    constitution_assessed_at: str | None = None
    constitution_reassessment_cycle_days: int | None = None
    tongue_image_url: str | None = None
    tongue_color: str | None = None
    tongue_coating: str | None = None
    tongue_shape: str | None = None
    tongue_constitution_hint: str | None = None
    tongue_raw_description: str | None = None
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
