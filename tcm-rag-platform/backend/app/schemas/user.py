"""用户相关 schema。"""

from pydantic import BaseModel


class UserProfile(BaseModel):
    id: int
    username: str
    email: str
    role: str
    status: str = "active"
    created_at: str


class UserRoleUpdateRequest(BaseModel):
    role: str
