"""用户相关 schema。"""

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    id: int
    username: str
    email: str
    role: str
    status: str = "active"
    created_at: str


class UserRoleUpdateRequest(BaseModel):
    role: str


class UserCaseProfileBase(BaseModel):
    gender: str | None = None
    age: int | None = None
    chief_complaint: str | None = None
    symptom_duration: str | None = None
    primary_symptoms: list[str] = Field(default_factory=list)
    has_visited_doctor: bool = False
    currently_taking_medicine: bool = False
    medication_details: str | None = None
    sleep_status: str | None = None
    appetite_status: str | None = None
    bowel_status: str | None = None
    tongue_description: str | None = None
    medical_history: str | None = None
    allergy_history: str | None = None
    menstrual_history: str | None = None


class UserCaseProfileUpsert(UserCaseProfileBase):
    pass


class UserCaseProfileOut(UserCaseProfileBase):
    id: int | None = None
    user_id: int | None = None
    profile_completed: bool = False
    summary: str = ""
    created_at: str | None = None
    updated_at: str | None = None
