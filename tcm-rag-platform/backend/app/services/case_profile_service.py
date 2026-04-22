"""多角色基础档案服务。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from app.core.config import settings
from app.core.exceptions import BadRequestError, ResourceNotFoundError
from app.core.logger import get_logger
from app.models.case_profile import CaseProfile
from app.services.portrait_memory_service import portrait_memory_service
from app.services.tongue_analysis_service import tongue_analysis_service

logger = get_logger(__name__)

_ALLOWED_TONGUE_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
}
_ALLOWED_TONGUE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
_MAX_TONGUE_IMAGE_SIZE = 8 * 1024 * 1024


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_string_list_input(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.replace("，", "、").split("、")
    elif isinstance(value, list):
        raw_items = value
    else:
        return []
    normalized: list[str] = []
    for item in raw_items:
        text = _normalize_text(str(item) if item is not None else None)
        if text and text not in normalized:
            normalized.append(text)
    return normalized


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
    long_term_profile = portrait_memory_service.build_long_term_profile(
        profile,
        allergy_history=profile.allergy_history,
        medical_history=profile.medical_history,
    )
    primary_constitution = long_term_profile.get("primary_constitution")
    secondary_constitutions = long_term_profile.get("secondary_constitutions") or []
    if primary_constitution:
        constitution_text = f"长期体质：{primary_constitution}"
        if secondary_constitutions:
            constitution_text += f"（兼{ '、'.join(secondary_constitutions[:2]) }）"
        parts.append(constitution_text)
    if long_term_profile.get("chronic_symptoms"):
        parts.append(f"长期症状：{'、'.join(long_term_profile['chronic_symptoms'][:4])}")
    if long_term_profile.get("dietary_restrictions"):
        parts.append(f"饮食禁忌：{'、'.join(long_term_profile['dietary_restrictions'][:4])}")
    if long_term_profile.get("tongue_coating"):
        tongue_text = f"舌诊：{long_term_profile['tongue_coating']}"
        if long_term_profile.get("tongue_color"):
            tongue_text = f"舌诊：{long_term_profile['tongue_color']}，{long_term_profile['tongue_coating']}"
        parts.append(tongue_text)
    if profile.notes:
        parts.append(f"备注：{profile.notes}")
    return "；".join(parts)


def serialize_case_profile(profile: CaseProfile) -> dict:
    long_term_fields = portrait_memory_service.serialize_long_term_profile_fields(
        profile,
        allergy_history=profile.allergy_history,
        medical_history=profile.medical_history,
    )
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
        **long_term_fields,
        "tags": profile.tags or [],
        "profile_completed": is_case_profile_complete(profile),
        "summary": build_case_profile_summary(profile),
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


class CaseProfileService:
    @staticmethod
    def _validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
        normalized = payload.copy()
        normalized["profile_name"] = _normalize_text(normalized.get("profile_name"))
        normalized["gender"] = _normalize_text(normalized.get("gender"))
        normalized["medical_history"] = _normalize_text(normalized.get("medical_history"))
        normalized["allergy_history"] = _normalize_text(normalized.get("allergy_history"))
        normalized["current_medications"] = _normalize_text(normalized.get("current_medications"))
        normalized["menstrual_history"] = _normalize_text(normalized.get("menstrual_history"))
        normalized["notes"] = _normalize_text(normalized.get("notes"))
        normalized["chronic_symptoms"] = _normalize_string_list_input(normalized.get("chronic_symptoms"))
        normalized["dietary_restrictions"] = _normalize_string_list_input(normalized.get("dietary_restrictions"))
        normalized["constitution_secondary"] = _normalize_string_list_input(normalized.get("constitution_secondary"))
        normalized["constitution_primary"] = _normalize_text(normalized.get("constitution_primary"))
        normalized["tongue_image_url"] = _normalize_text(normalized.get("tongue_image_url"))
        normalized["tongue_color"] = _normalize_text(normalized.get("tongue_color"))
        normalized["tongue_coating"] = _normalize_text(normalized.get("tongue_coating"))
        normalized["tongue_shape"] = _normalize_text(normalized.get("tongue_shape"))
        normalized["tongue_constitution_hint"] = _normalize_text(normalized.get("tongue_constitution_hint"))
        normalized["tongue_raw_description"] = _normalize_text(normalized.get("tongue_raw_description"))
        raw_assessed_at = _normalize_text(normalized.get("constitution_assessed_at"))
        normalized.update(
            portrait_memory_service.normalize_long_term_profile_payload(
                normalized,
                allergy_history=normalized.get("allergy_history"),
                medical_history=normalized.get("medical_history"),
            )
        )
        normalized["tags"] = [item.strip() for item in normalized.get("tags", []) if item and item.strip()]

        # Remove legacy nested payload if present.
        normalized.pop("constitution_profile", None)

        if normalized.get("constitution_primary") is not None and normalized["constitution_primary"] not in {
            "平和", "气虚", "阳虚", "阴虚", "痰湿", "湿热", "血瘀", "气郁", "特禀"
        }:
            raise BadRequestError(message="主体质取值不合法")

        if normalized.get("constitution_reassessment_cycle_days") is not None and normalized[
            "constitution_reassessment_cycle_days"
        ] <= 0:
            raise BadRequestError(message="体质复评周期必须大于 0")

        if raw_assessed_at and normalized.get("constitution_assessed_at") is None:
            raise BadRequestError(message="体质测评日期格式不正确，请使用 YYYY-MM-DD")

        score_fields = (
            "constitution_pinghe_score",
            "constitution_qixu_score",
            "constitution_yangxu_score",
            "constitution_yinxu_score",
            "constitution_tanshi_score",
            "constitution_shire_score",
            "constitution_xueyu_score",
            "constitution_qiyu_score",
            "constitution_tebing_score",
        )
        for field_name in score_fields:
            value = normalized.get(field_name)
            if value is not None and not (0 <= value <= 100):
                raise BadRequestError(message=f"{field_name} 需要在 0-100 之间")

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

    async def upload_tongue_image(self, db, repo, user_id: int, profile_id: int, file: UploadFile) -> dict:
        profile = await self.get_profile_or_raise(db, repo, user_id, profile_id)
        suffix = Path(file.filename or "").suffix.lower()
        content_type = (file.content_type or "").lower()
        if content_type not in _ALLOWED_TONGUE_IMAGE_TYPES and suffix not in _ALLOWED_TONGUE_IMAGE_EXTENSIONS:
            raise BadRequestError(message="舌像仅支持 PNG 或 JPG 格式")

        content = await file.read()
        if not content:
            raise BadRequestError(message="上传的舌像为空")
        if len(content) > _MAX_TONGUE_IMAGE_SIZE:
            raise BadRequestError(message="舌像大小不能超过 8MB")

        ext = _ALLOWED_TONGUE_IMAGE_TYPES.get(content_type)
        if ext is None:
            ext = ".png" if suffix == ".png" else ".jpg"

        media_root = Path(settings.MEDIA_DIR)
        upload_dir = media_root / "tongue-images" / f"user-{user_id}" / f"profile-{profile_id}"
        upload_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid4().hex}{ext}"
        file_path = upload_dir / filename
        file_path.write_bytes(content)

        # AI tongue analysis
        analysis_result = await tongue_analysis_service.analyze_tongue(str(file_path))
        if analysis_result:
            logger.info("舌像 AI 分析完成: %s", analysis_result)

        previous_url = _normalize_text(profile.tongue_image_url)
        if previous_url and previous_url.startswith("/media/"):
            relative_path = previous_url.removeprefix("/media/").lstrip("/")
            old_file = (media_root / relative_path).resolve()
            media_root_resolved = media_root.resolve()
            if media_root_resolved in old_file.parents and old_file.exists() and old_file.is_file():
                try:
                    old_file.unlink()
                except OSError:
                    pass

        update_payload = {
            "tongue_image_url": f"/media/tongue-images/user-{user_id}/profile-{profile_id}/{filename}",
            **analysis_result,
        }
        profile = await repo.update(db, profile=profile, payload=update_payload)
        profile.profile_completed = is_case_profile_complete(profile)
        await db.flush()
        await db.refresh(profile)
        return serialize_case_profile(profile)


case_profile_service = CaseProfileService()
