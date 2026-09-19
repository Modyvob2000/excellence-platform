import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app import auth_core  # noqa: E402


class TestPasswordHashing(unittest.TestCase):
    def test_hash_and_verify_correct_password(self):
        h = auth_core.hash_password("MySecret123!")
        self.assertTrue(auth_core.verify_password("MySecret123!", h))

    def test_verify_rejects_wrong_password(self):
        h = auth_core.hash_password("MySecret123!")
        self.assertFalse(auth_core.verify_password("WrongPassword", h))

    def test_hash_is_salted_and_unique_each_time(self):
        h1 = auth_core.hash_password("same-password")
        h2 = auth_core.hash_password("same-password")
        self.assertNotEqual(h1, h2, "يجب أن يختلف الهاش حتى لنفس كلمة المرور (Salt عشوائي)")
        self.assertTrue(auth_core.verify_password("same-password", h1))
        self.assertTrue(auth_core.verify_password("same-password", h2))

    def test_empty_password_rejected(self):
        with self.assertRaises(ValueError):
            auth_core.hash_password("")

    def test_verify_garbage_hash_returns_false_not_exception(self):
        self.assertFalse(auth_core.verify_password("x", "not-a-real-hash"))


class TestJWT(unittest.TestCase):
    SECRET = "test-secret-key-for-unit-tests-only"

    def test_create_and_decode_token(self):
        token = auth_core.create_access_token(1, "ahmed", "TEACHER", self.SECRET)
        payload = auth_core.decode_access_token(token, self.SECRET)
        self.assertEqual(payload["sub"], "1")
        self.assertEqual(payload["username"], "ahmed")
        self.assertEqual(payload["role"], "TEACHER")

    def test_expired_token_raises_auth_error(self):
        token = auth_core.create_access_token(1, "ahmed", "TEACHER", self.SECRET,
                                               expires_in_seconds=-10)
        with self.assertRaises(auth_core.AuthError):
            auth_core.decode_access_token(token, self.SECRET)

    def test_wrong_secret_raises_auth_error(self):
        token = auth_core.create_access_token(1, "ahmed", "TEACHER", self.SECRET)
        with self.assertRaises(auth_core.AuthError):
            auth_core.decode_access_token(token, "a-completely-different-secret")

    def test_tampered_token_raises_auth_error(self):
        token = auth_core.create_access_token(1, "ahmed", "STUDENT", self.SECRET)
        tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
        with self.assertRaises(auth_core.AuthError):
            auth_core.decode_access_token(tampered, self.SECRET)

    def test_get_secret_key_requires_env_var(self):
        old = os.environ.pop("JWT_SECRET_KEY", None)
        try:
            with self.assertRaises(auth_core.AuthError):
                auth_core.get_secret_key()
        finally:
            if old is not None:
                os.environ["JWT_SECRET_KEY"] = old

    def test_get_secret_key_reads_env_var_when_set(self):
        os.environ["JWT_SECRET_KEY"] = "some-secret"
        try:
            self.assertEqual(auth_core.get_secret_key(), "some-secret")
        finally:
            del os.environ["JWT_SECRET_KEY"]


class TestRBAC(unittest.TestCase):
    def test_role_hierarchy_ordering(self):
        self.assertTrue(auth_core.has_role_at_least("SUPER_ADMIN", "STUDENT"))
        self.assertTrue(auth_core.has_role_at_least("ADMIN", "TEACHER"))
        self.assertFalse(auth_core.has_role_at_least("STUDENT", "TEACHER"))
        self.assertFalse(auth_core.has_role_at_least("TEACHER", "ADMIN"))

    def test_unknown_role_is_never_sufficient(self):
        self.assertFalse(auth_core.has_role_at_least("HACKER", "STUDENT"))

    def test_can_approve_question_permissions(self):
        self.assertTrue(auth_core.can_approve_question("REVIEWER"))
        self.assertTrue(auth_core.can_approve_question("ADMIN"))
        self.assertFalse(auth_core.can_approve_question("STUDENT"))

    def test_can_manage_users_permissions(self):
        self.assertTrue(auth_core.can_manage_users("ADMIN"))
        self.assertTrue(auth_core.can_manage_users("SUPER_ADMIN"))
        self.assertFalse(auth_core.can_manage_users("TEACHER"))
        self.assertFalse(auth_core.can_manage_users("REVIEWER"))

    def test_student_is_view_only(self):
        self.assertTrue(auth_core.can_view_only("STUDENT"))
        self.assertFalse(auth_core.can_edit_content("STUDENT"))
        self.assertFalse(auth_core.can_approve_question("STUDENT"))

    def test_require_role_raises_when_insufficient(self):
        with self.assertRaises(auth_core.AuthError):
            auth_core.require_role("STUDENT", "TEACHER")
        with self.assertRaises(auth_core.AuthError):
            auth_core.require_role(None, "STUDENT")

    def test_require_role_passes_silently_when_sufficient(self):
        try:
            auth_core.require_role("ADMIN", "TEACHER")
        except auth_core.AuthError:
            self.fail("require_role رفع خطأ رغم أن الصلاحية كافية.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
