"""
Auth API — Register / Login باستخدام auth_core المُختبر (انظر app/tests/test_auth_core.py).
⚠️ غير مُختبر عبر FastAPI TestClient فعليًا في هذه البيئة (FastAPI غير مثبَّتة هنا).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auth_core
from app.database import get_db
from app.models import Role, User

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str | None = None
    role_code: str = "STUDENT"


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


@router.post("/register", response_model=TokenResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=409, detail="اسم المستخدم مستخدم بالفعل.")
    role = db.query(Role).filter(Role.code == payload.role_code).first()
    if not role:
        raise HTTPException(status_code=400, detail="دور غير معروف.")
    user = User(
        username=payload.username,
        password_hash=auth_core.hash_password(payload.password),
        full_name=payload.full_name,
        role_id=role.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = auth_core.create_access_token(user.id, user.username, role.code,
                                           auth_core.get_secret_key())
    return TokenResponse(access_token=token, role=role.code)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not auth_core.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="بيانات الدخول غير صحيحة.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="الحساب غير مُفعَّل.")
    token = auth_core.create_access_token(user.id, user.username, user.role.code,
                                           auth_core.get_secret_key())
    return TokenResponse(access_token=token, role=user.role.code)
