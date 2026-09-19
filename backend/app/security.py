"""
FastAPI dependency layer over app/auth_core.py (المُختبر فعليًا).
⚠️ هذا الملف نفسه (طبقة FastAPI الرقيقة) غير مُشغَّل هنا لعدم توفر FastAPI،
لكنه يستدعي auth_core الذي اجتاز 18 اختبارًا حقيقيًا (raise/decode/RBAC).
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import auth_core

bearer_scheme = HTTPBearer()


@dataclass
class CurrentUser:
    id: int
    username: str
    role: str


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> CurrentUser:
    try:
        payload = auth_core.decode_access_token(credentials.credentials, auth_core.get_secret_key())
    except auth_core.AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    return CurrentUser(id=int(payload["sub"]), username=payload["username"], role=payload["role"])


def require_roles(*allowed_roles: str):
    """Dependency factory: يرفع 403 إن لم يكن دور المستخدم ضمن المسموح."""
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed_roles and "SUPER_ADMIN" != user.role:
            raise HTTPException(status_code=403, detail=f"هذه العملية تتطلب أحد الأدوار: {allowed_roles}")
        return user
    return dependency
