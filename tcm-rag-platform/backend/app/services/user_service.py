"""用户服务。"""

from __future__ import annotations

from app.core.exceptions import BadRequestError, ResourceNotFoundError
from app.models.role import RoleName
from app.models.user import User
from app.models.user_case_profile import UserCaseProfile


def get_primary_role(user: User) -> str:
    if not user.roles:
        return RoleName.USER.value
    role = user.roles[0].name
    return role.value if hasattr(role, "value") else str(role)


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": get_primary_role(user),
        "status": user.status.value if hasattr(user.status, "value") else str(user.status),
        "created_at": user.created_at,
    }


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def is_case_profile_complete(profile: UserCaseProfile | None) -> bool:
    if profile is None:
        return False
    return all(
        [
            _normalize_text(profile.gender),
            profile.age is not None,
            _normalize_text(profile.chief_complaint),
            _normalize_text(profile.symptom_duration),
            bool(profile.primary_symptoms),
        ]
    )


def build_case_profile_summary(profile: UserCaseProfile | None) -> str:
    if profile is None or not is_case_profile_complete(profile):
        return ""

    parts: list[str] = []
    if profile.gender:
        parts.append(profile.gender)
    if profile.age is not None:
        parts.append(f"{profile.age}岁")
    if profile.chief_complaint:
        parts.append(f"主诉{profile.chief_complaint}")
    if profile.symptom_duration:
        parts.append(f"病程{profile.symptom_duration}")
    if profile.primary_symptoms:
        parts.append(f"主要症状：{'、'.join(profile.primary_symptoms[:4])}")
    parts.append("已就医" if profile.has_visited_doctor else "尚未线下就医")
    parts.append("正在用药" if profile.currently_taking_medicine else "当前未用药")
    if profile.sleep_status:
        parts.append(f"睡眠：{profile.sleep_status}")
    if profile.tongue_description:
        parts.append(f"舌象描述：{profile.tongue_description}")
    return "；".join(parts)


def serialize_case_profile(profile: UserCaseProfile | None, user_id: int) -> dict:
    if profile is None:
        return {
            "id": None,
            "user_id": user_id,
            "gender": None,
            "age": None,
            "chief_complaint": None,
            "symptom_duration": None,
            "primary_symptoms": [],
            "has_visited_doctor": False,
            "currently_taking_medicine": False,
            "medication_details": None,
            "sleep_status": None,
            "appetite_status": None,
            "bowel_status": None,
            "tongue_description": None,
            "medical_history": None,
            "allergy_history": None,
            "menstrual_history": None,
            "profile_completed": False,
            "summary": "",
            "created_at": None,
            "updated_at": None,
        }

    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "gender": profile.gender,
        "age": profile.age,
        "chief_complaint": profile.chief_complaint,
        "symptom_duration": profile.symptom_duration,
        "primary_symptoms": profile.primary_symptoms or [],
        "has_visited_doctor": profile.has_visited_doctor,
        "currently_taking_medicine": profile.currently_taking_medicine,
        "medication_details": profile.medication_details,
        "sleep_status": profile.sleep_status,
        "appetite_status": profile.appetite_status,
        "bowel_status": profile.bowel_status,
        "tongue_description": profile.tongue_description,
        "medical_history": profile.medical_history,
        "allergy_history": profile.allergy_history,
        "menstrual_history": profile.menstrual_history,
        "profile_completed": is_case_profile_complete(profile),
        "summary": build_case_profile_summary(profile),
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


class UserService:
    async def get_user_or_raise(self, db, user_repo, user_id: int) -> User:
        user = await user_repo.get_by_id(db, user_id)
        if not user:
            raise ResourceNotFoundError(message="用户不存在")
        return user

    async def get_case_profile(self, db, user_repo, user_id: int) -> dict:
        user = await self.get_user_or_raise(db, user_repo, user_id)
        profile = await user_repo.get_case_profile_by_user_id(db, user_id)
        return serialize_case_profile(profile, user.id)

    async def upsert_case_profile(self, db, user_repo, user_id: int, payload) -> dict:
        await self.get_user_or_raise(db, user_repo, user_id)
        profile_data = payload.model_dump()
        profile_data["gender"] = _normalize_text(profile_data.get("gender"))
        profile_data["chief_complaint"] = _normalize_text(profile_data.get("chief_complaint"))
        profile_data["symptom_duration"] = _normalize_text(profile_data.get("symptom_duration"))
        profile_data["medication_details"] = _normalize_text(profile_data.get("medication_details"))
        profile_data["sleep_status"] = _normalize_text(profile_data.get("sleep_status"))
        profile_data["appetite_status"] = _normalize_text(profile_data.get("appetite_status"))
        profile_data["bowel_status"] = _normalize_text(profile_data.get("bowel_status"))
        profile_data["tongue_description"] = _normalize_text(profile_data.get("tongue_description"))
        profile_data["medical_history"] = _normalize_text(profile_data.get("medical_history"))
        profile_data["allergy_history"] = _normalize_text(profile_data.get("allergy_history"))
        profile_data["menstrual_history"] = _normalize_text(profile_data.get("menstrual_history"))
        profile_data["primary_symptoms"] = [
            item.strip() for item in profile_data.get("primary_symptoms", []) if item and item.strip()
        ]

        age = profile_data.get("age")
        if age is not None and (age <= 0 or age > 120):
            raise BadRequestError(message="年龄范围不合法")

        if profile_data["currently_taking_medicine"] is False:
            profile_data["medication_details"] = None

        profile = await user_repo.upsert_case_profile(
            db,
            user_id=user_id,
            profile_data=profile_data,
        )
        profile.profile_completed = is_case_profile_complete(profile)
        await db.flush()
        await db.refresh(profile)
        return serialize_case_profile(profile, user_id)


user_service = UserService()
