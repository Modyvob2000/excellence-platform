"""Users/Admin API — إدارة المستخدمين والأدوار. ⚠️ غير مُشغَّل عبر HTTP هنا."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Role, User
from app.security import CurrentUser, get_current_user, require_roles
from app.services.audit_service import record as audit_record
from app.services.user_service import (
    UserData, UserServiceError, change_role, create_user, deactivate_user, list_users,
    reactivate_user, reset_password,
)

router = APIRouter(prefix="/users", tags=["users"])


class SqlAlchemyUserStore:
    def __init__(self, db: Session):
        self.db = db

    def _to_data(self, row: User) -> UserData:
        return UserData(id=row.id, username=row.username, password_hash=row.password_hash,
                         full_name=row.full_name, role=row.role.code, is_active=row.is_active)

    def insert(self, data: UserData) -> int:
        role = self.db.query(Role).filter(Role.code == data.role).first()
        if not role:
            raise UserServiceError(f"دور غير مهيّأ في قاعدة البيانات: {data.role}")
        row = User(username=data.username, password_hash=data.password_hash,
                    full_name=data.full_name, role_id=role.id, is_active=data.is_active)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row.id

    def get(self, user_id: int) -> Optional[UserData]:
        row = self.db.get(User, user_id)
        return self._to_data(row) if row else None

    def get_by_username(self, username: str) -> Optional[UserData]:
        row = self.db.query(User).filter(User.username == username).first()
        return self._to_data(row) if row else None

    def update(self, user_id: int, patch: dict) -> UserData:
        row = self.db.get(User, user_id)
        if not row:
            raise UserServiceError(f"المستخدم #{user_id} غير موجود.")
        if "role" in patch:
            role = self.db.query(Role).filter(Role.code == patch.pop("role")).first()
            row.role_id = role.id
        for key, value in patch.items():
            setattr(row, key, value)
        self.db.commit()
        self.db.refresh(row)
        return self._to_data(row)

    def list(self, role: Optional[str] = None, active_only: bool = False) -> List[UserData]:
        q = self.db.query(User)
        if role:
            q = q.join(Role).filter(Role.code == role)
        if active_only:
            q = q.filter(User.is_active.is_(True))
        return [self._to_data(r) for r in q.all()]


def get_store(db: Session = Depends(get_db)) -> SqlAlchemyUserStore:
    return SqlAlchemyUserStore(db)


class UserCreateIn(BaseModel):
    username: str
    password: str
    role: str = "STUDENT"
    full_name: Optional[str] = None


class UserOut(BaseModel):
    id: int
    username: str
    full_name: Optional[str]
    role: str
    is_active: bool

    @classmethod
    def from_data(cls, d: UserData) -> "UserOut":
        return cls(id=d.id, username=d.username, full_name=d.full_name, role=d.role, is_active=d.is_active)


@router.post("", response_model=UserOut)
def create(payload: UserCreateIn, store: SqlAlchemyUserStore = Depends(get_store),
           db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    try:
        created = create_user(store, user.role, payload.username, payload.password,
                               role=payload.role, full_name=payload.full_name)
    except UserServiceError as e:
        raise HTTPException(400, str(e)) from e
    audit_record(_AuditAdapter(db), user.id, "CREATE_USER", "user", created.id, new_role=payload.role)
    return UserOut.from_data(created)


@router.get("", response_model=List[UserOut])
def list_all(role: Optional[str] = None, active_only: bool = False,
             store: SqlAlchemyUserStore = Depends(get_store),
             user: CurrentUser = Depends(require_roles("ADMIN", "SUPER_ADMIN"))):
    try:
        users = list_users(store, user.role, role=role, active_only=active_only)
    except UserServiceError as e:
        raise HTTPException(403, str(e)) from e
    return [UserOut.from_data(u) for u in users]


@router.post("/{user_id}/deactivate")
def deactivate(user_id: int, store: SqlAlchemyUserStore = Depends(get_store), db: Session = Depends(get_db),
                user: CurrentUser = Depends(require_roles("ADMIN", "SUPER_ADMIN"))):
    try:
        deactivate_user(store, user.role, user_id)
    except UserServiceError as e:
        raise HTTPException(403, str(e)) from e
    audit_record(_AuditAdapter(db), user.id, "DEACTIVATE_USER", "user", user_id)
    return {"status": "deactivated"}


@router.post("/{user_id}/reactivate")
def reactivate(user_id: int, store: SqlAlchemyUserStore = Depends(get_store), db: Session = Depends(get_db),
                user: CurrentUser = Depends(require_roles("ADMIN", "SUPER_ADMIN"))):
    try:
        reactivate_user(store, user.role, user_id)
    except UserServiceError as e:
        raise HTTPException(403, str(e)) from e
    audit_record(_AuditAdapter(db), user.id, "REACTIVATE_USER", "user", user_id)
    return {"status": "reactivated"}


@router.post("/{user_id}/role")
def set_role(user_id: int, new_role: str, store: SqlAlchemyUserStore = Depends(get_store),
             db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("SUPER_ADMIN"))):
    try:
        change_role(store, user.role, user_id, new_role)
    except UserServiceError as e:
        raise HTTPException(403, str(e)) from e
    audit_record(_AuditAdapter(db), user.id, "CHANGE_ROLE", "user", user_id, new_role=new_role)
    return {"status": "role_changed", "role": new_role}


@router.post("/{user_id}/reset-password")
def reset_pw(user_id: int, new_password: str, store: SqlAlchemyUserStore = Depends(get_store),
             db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "SUPER_ADMIN"))):
    try:
        reset_password(store, user.role, user_id, new_password)
    except UserServiceError as e:
        raise HTTPException(403, str(e)) from e
    audit_record(_AuditAdapter(db), user.id, "RESET_PASSWORD", "user", user_id)
    return {"status": "password_reset"}


class _AuditAdapter:
    """محول رفيع لتسجيل audit_service.record مباشرة في جدول audit_logs."""
    def __init__(self, db: Session):
        self.db = db

    def insert(self, entry) -> int:
        from app.models import AuditLog
        row = AuditLog(user_id=entry.user_id, action=entry.action, entity=entry.entity,
                        entity_id=entry.entity_id, details_json=entry.details)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row.id
