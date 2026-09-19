"""
User/Admin Service — إدارة المستخدمين والأدوار. منطق خالص عبر UserStore
(Protocol)، مفصول عن FastAPI/SQLAlchemy — قابل للاختبار الكامل بمخزن وهمي.

RBAC الفعلي (من يملك صلاحية فعل ماذا) يعتمد على app/auth_core.py المُختبر
(can_manage_users, has_role_at_least) — هذه الوحدة لا تُعيد تعريف قواعد
الصلاحيات، فقط تستدعيها قبل أي عملية حساسة.
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from app import auth_core

VALID_ROLES = ("STUDENT", "REVIEWER", "TEACHER", "ADMIN", "SUPER_ADMIN")
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.\u0600-\u06FF]{3,50}$")


class UserServiceError(Exception):
    pass


@dataclass
class UserData:
    id: Optional[int]
    username: str
    password_hash: str
    full_name: Optional[str] = None
    role: str = "STUDENT"
    is_active: bool = True


class UserStore(Protocol):
    def insert(self, data: UserData) -> int: ...
    def get(self, user_id: int) -> Optional[UserData]: ...
    def get_by_username(self, username: str) -> Optional[UserData]: ...
    def update(self, user_id: int, patch: dict) -> UserData: ...
    def list(self, role: Optional[str] = None, active_only: bool = False) -> List[UserData]: ...


def _validate_username(username: str):
    if not username or not USERNAME_PATTERN.match(username):
        raise UserServiceError(
            "اسم المستخدم غير صالح (3-50 حرفًا، أحرف/أرقام/عربي/._ فقط).")


def create_user(store: UserStore, acting_role: str, username: str, password: str,
                 role: str = "STUDENT", full_name: Optional[str] = None) -> UserData:
    if not auth_core.can_manage_users(acting_role) and role != "STUDENT":
        raise UserServiceError("لا تملك صلاحية إنشاء مستخدم بهذا الدور.")
    if role not in VALID_ROLES:
        raise UserServiceError(f"دور غير معروف: {role}")
    _validate_username(username)
    if store.get_by_username(username):
        raise UserServiceError("اسم المستخدم مستخدم بالفعل.")
    if len(password) < 8:
        raise UserServiceError("كلمة المرور يجب ألا تقل عن 8 أحرف.")

    data = UserData(id=None, username=username, password_hash=auth_core.hash_password(password),
                     full_name=full_name, role=role, is_active=True)
    data.id = store.insert(data)
    return data


def deactivate_user(store: UserStore, acting_role: str, user_id: int) -> UserData:
    if not auth_core.can_manage_users(acting_role):
        raise UserServiceError("لا تملك صلاحية تعطيل الحسابات.")
    return store.update(user_id, {"is_active": False})


def reactivate_user(store: UserStore, acting_role: str, user_id: int) -> UserData:
    if not auth_core.can_manage_users(acting_role):
        raise UserServiceError("لا تملك صلاحية تفعيل الحسابات.")
    return store.update(user_id, {"is_active": True})


def change_role(store: UserStore, acting_role: str, user_id: int, new_role: str) -> UserData:
    if acting_role != "SUPER_ADMIN":
        raise UserServiceError("تغيير الأدوار يتطلب صلاحية SUPER_ADMIN.")
    if new_role not in VALID_ROLES:
        raise UserServiceError(f"دور غير معروف: {new_role}")
    return store.update(user_id, {"role": new_role})


def reset_password(store: UserStore, acting_role: str, user_id: int, new_password: str) -> UserData:
    if not auth_core.can_manage_users(acting_role):
        raise UserServiceError("لا تملك صلاحية إعادة تعيين كلمات المرور.")
    if len(new_password) < 8:
        raise UserServiceError("كلمة المرور يجب ألا تقل عن 8 أحرف.")
    return store.update(user_id, {"password_hash": auth_core.hash_password(new_password)})


def list_users(store: UserStore, acting_role: str, role: Optional[str] = None,
               active_only: bool = False) -> List[UserData]:
    if not auth_core.can_manage_users(acting_role):
        raise UserServiceError("لا تملك صلاحية عرض قائمة المستخدمين.")
    return store.list(role=role, active_only=active_only)
