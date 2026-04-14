"""多角色基础档案服务。"""

from __future__ import annotations

from app.core.exceptions import BadRequestError, ResourceNotFoundError
from app.models.case_profile import CaseProfile


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def is_case_profile_complete(profile: CaseProfile | None) -> bool:
    if profile is None:
        return False
    return all(
        [
            _normalize_text(profile.profile_name),
            _normalize_text(profile.gender),
            profile.age is not None,
        ]
    )


def build_case_profile_summary(profile: CaseProfile | None) -> str:
    if profile is None:
        return ""

    parts: list[str] = [profile.profile_name]
    if profile.gender:
        parts.append(profile.gender)
    if profile.age is not None:
        parts.append(f"{profile.age}岁")
    if profile.height_cm:
        parts.append(f"身高{profile.height_cm}cm")
    if profile.weight_kg:
        parts.append(f"体重{profile.weight_kg}kg")
    if profile.medical_history:
        parts.append(f"既往史：{profile.medical_history}")
    if profile.current_medications:
        parts.append(f"当前用药：{profile.current_medications}")
    if profile.allergy_history:
        parts.append(f"过敏史：{profile.allergy_history}")
    if profile.notes:
        parts.append(f"备注：{profile.notes}")
    return "；".join(parts)


def serialize_case_profile(profile: CaseProfile) -> dict:
    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "profile_name": profile.profile_name,
        "gender": profile.gender,
        "age": profile.age,
        "height_cm": profile.height_cm,
        "weight_kg": profile.weight_kg,
        "medical_history": profile.medical_history,
        "allergy_history": profile.allergy_history,
        "current_medications": profile.current_medications,
        "menstrual_history": profile.menstrual_history,
        "notes": profile.notes,
        "tags": profile.tags or [],
        "profile_completed": is_case_profile_complete(profile),
        "summary": build_case_profile_summary(profile),
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


class CaseProfileService:
    @staticmethod
    def _validate_payload(payload: dict) -> dict:
        normalized = payload.copy()
        normalized["profile_name"] = _normalize_text(normalized.get("profile_name"))
        normalized["gender"] = _normalize_text(normalized.get("gender"))
        normalized["medical_history"] = _normalize_text(normalized.get("medical_history"))
        normalized["allergy_history"] = _normalize_text(normalized.get("allergy_history"))
        normalized["current_medications"] = _normalize_text(normalized.get("current_medications"))
        normalized["menstrual_history"] = _normalize_text(normalized.get("menstrual_history"))
        normalized["notes"] = _normalize_text(normalized.get("notes"))
        normalized["tags"] = [item.strip() for item in normalized.get("tags", []) if item and item.strip()]

        if not normalized["profile_name"]:
            raise BadRequestError(message="请填写角色名称")

        age = normalized.get("age")
        if age is not None and (age <= 0 or age > 120):
            raise BadRequestError(message="年龄范围不合法")

        for field_name in ("height_cm", "weight_kg"):
            value = normalized.get(field_name)
            if value is not None and value <= 0:
                raise BadRequestError(message=f"{field_name} 不能小于等于 0")

        return normalized

    async def list_profiles(self, db, repo, user_id: int) -> list[dict]:
        profiles = await repo.list_by_user_id(db, user_id)
        return [serialize_case_profile(profile) for profile in profiles]

    async def create_profile(self, db, repo, user_id: int, payload) -> dict:
        profile_data = self._validate_payload(payload.model_dump())
        profile = await repo.create(db, user_id=user_id, payload=profile_data)
        profile.profile_completed = is_case_profile_complete(profile)
        await db.flush()
        await db.refresh(profile)
        return serialize_case_profile(profile)

    async def update_profile(self, db, repo, user_id: int, profile_id: int, payload) -> dict:
        profile = await repo.get_by_id_and_user_id(db, profile_id=profile_id, user_id=user_id)
        if not profile:
            raise ResourceNotFoundError(message="角色档案不存在")

        profile_data = self._validate_payload(payload.model_dump())
        profile = await repo.update(db, profile=profile, payload=profile_data)
        profile.profile_completed = is_case_profile_complete(profile)
        await db.flush()
        await db.refresh(profile)
        return serialize_case_profile(profile)

    async def get_profile_or_raise(self, db, repo, user_id: int, profile_id: int) -> CaseProfile:
        profile = await repo.get_by_id_and_user_id(db, profile_id=profile_id, user_id=user_id)
        if not profile:
            raise ResourceNotFoundError(message="角色档案不存在")
        return profile


case_profile_service = CaseProfileService()
