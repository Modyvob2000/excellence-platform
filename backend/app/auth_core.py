"""
auth_core — منطق المصادقة والصلاحيات، معزول تمامًا عن FastAPI.

هذا الملف عمدًا لا يعتمد على FastAPI أو SQLAlchemy، فقط على المكتبة
القياسية (hashlib/hmac/secrets) وعلى PyJWT (متوفرة فعليًا في هذه البيئة
وتم اختبارها). الهدف: منطق المصادقة والصلاحيات يجب أن يكون قابلاً للاختبار
الحقيقي بدون الحاجة لخادم أو قاعدة بيانات، ثم تستدعيه طبقة FastAPI الرقيقة
في routers/auth.py.

✅ هذا الملف تم اختباره فعليًا في هذه البيئة (انظر backend/app/tests/test_auth_core.py).
"""
import hashlib
import hmac
import os
import secrets
import time
from typing import Optional

import jwt  # PyJWT

PBKDF2_ITERATIONS = 260_000
PBKDF2_ALGO = "sha256"

JWT_ALGORITHM = "HS256"
JWT_DEFAULT_EXPIRY_SECONDS = 60 * 60 * 8  # 8 ساعات

# ترتيب الصلاحيات من الأعلى للأقل، يُستخدم في has_role_at_least
ROLE_HIERARCHY = ["STUDENT", "REVIEWER", "TEACHER", "ADMIN", "SUPER_ADMIN"]


class AuthError(Exception):
    pass


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-HMAC-SHA256, stdlib فقط، بدون أي حزمة خارجية)
# ---------------------------------------------------------------------------

def hash_password(plain_password: str) -> str:
    if not plain_password:
        raise ValueError("كلمة المرور لا يمكن أن تكون فارغة.")
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(PBKDF2_ALGO, plain_password.encode("utf-8"),
                              bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verify_password(plain_password: str, stored_hash: str) -> bool:
    try:
        algo_tag, iterations, salt, hex_digest = stored_hash.split("$")
        iterations = int(iterations)
    except (ValueError, AttributeError):
        return False
    if algo_tag != "pbkdf2_sha256":
        return False
    dk = hashlib.pbkdf2_hmac(PBKDF2_ALGO, plain_password.encode("utf-8"),
                              bytes.fromhex(salt), iterations)
    return hmac.compare_digest(dk.hex(), hex_digest)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def create_access_token(user_id: int, username: str, role: str, secret_key: str,
                         expires_in_seconds: int = JWT_DEFAULT_EXPIRY_SECONDS) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    return jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret_key: str) -> dict:
    try:
        return jwt.decode(token, secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise AuthError("انتهت صلاحية الجلسة، يرجى تسجيل الدخول مرة أخرى.") from e
    except jwt.InvalidTokenError as e:
        raise AuthError("رمز الدخول غير صالح.") from e


def get_secret_key() -> str:
    """يُقرأ من متغير بيئة السيرفر فقط — لا قيمة افتراضية سرية في الكود."""
    key = os.environ.get("JWT_SECRET_KEY")
    if not key:
        raise AuthError(
            "JWT_SECRET_KEY غير مضبوط في متغيرات البيئة. "
            "لا يجوز تشغيل السيرفر في الإنتاج بدونه.")
    return key


# ---------------------------------------------------------------------------
# RBAC — Role Based Access Control
# ---------------------------------------------------------------------------

def has_role_at_least(user_role: str, required_role: str) -> bool:
    """هل صلاحية المستخدم >= الصلاحية المطلوبة في التسلسل الهرمي؟"""
    try:
        return ROLE_HIERARCHY.index(user_role) >= ROLE_HIERARCHY.index(required_role)
    except ValueError:
        return False


def can_approve_question(user_role: str) -> bool:
    return user_role in ("REVIEWER", "TEACHER", "ADMIN", "SUPER_ADMIN")


def can_manage_users(user_role: str) -> bool:
    return user_role in ("ADMIN", "SUPER_ADMIN")


def can_edit_content(user_role: str) -> bool:
    return user_role in ("TEACHER", "ADMIN", "SUPER_ADMIN")


def can_view_only(user_role: str) -> bool:
    return user_role == "STUDENT"


def require_role(user_role: Optional[str], required_role: str):
    """يرفع AuthError إذا لم تتوفر الصلاحية الكافية — تُستخدم كـdependency في FastAPI."""
    if not user_role or not has_role_at_least(user_role, required_role):
        raise AuthError(f"هذه العملية تتطلب صلاحية {required_role} على الأقل.")
