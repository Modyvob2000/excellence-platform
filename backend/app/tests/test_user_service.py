import os
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app import auth_core  # noqa: E402
from app.services.user_service import (  # noqa: E402
    UserData, UserServiceError, change_role, create_user, deactivate_user, list_users,
    reactivate_user, reset_password,
)


class FakeUserStore:
    def __init__(self):
        self._next_id = 1
        self._data = {}

    def insert(self, data: UserData) -> int:
        uid = self._next_id
        self._next_id += 1
        data.id = uid
        self._data[uid] = data
        return uid

    def get(self, user_id):
        return self._data.get(user_id)

    def get_by_username(self, username):
        return next((u for u in self._data.values() if u.username == username), None)

    def update(self, user_id, patch):
        updated = replace(self._data[user_id], **patch)
        self._data[user_id] = updated
        return updated

    def list(self, role=None, active_only=False):
        results = list(self._data.values())
        if role:
            results = [u for u in results if u.role == role]
        if active_only:
            results = [u for u in results if u.is_active]
        return results


class TestCreateUser(unittest.TestCase):
    def test_admin_can_create_teacher(self):
        store = FakeUserStore()
        user = create_user(store, "ADMIN", "ahmed_t", "StrongPass123", role="TEACHER")
        self.assertEqual(user.role, "TEACHER")
        self.assertTrue(auth_core.verify_password("StrongPass123", user.password_hash))

    def test_anyone_can_self_register_as_student(self):
        store = FakeUserStore()
        user = create_user(store, "STUDENT", "new_student", "StrongPass123", role="STUDENT")
        self.assertEqual(user.role, "STUDENT")

    def test_student_cannot_create_teacher_account(self):
        store = FakeUserStore()
        with self.assertRaises(UserServiceError):
            create_user(store, "STUDENT", "sneaky", "StrongPass123", role="TEACHER")

    def test_duplicate_username_rejected(self):
        store = FakeUserStore()
        create_user(store, "ADMIN", "same_name", "StrongPass123", role="STUDENT")
        with self.assertRaises(UserServiceError):
            create_user(store, "ADMIN", "same_name", "AnotherPass123", role="STUDENT")

    def test_short_password_rejected(self):
        store = FakeUserStore()
        with self.assertRaises(UserServiceError):
            create_user(store, "ADMIN", "user1", "short", role="STUDENT")

    def test_invalid_username_rejected(self):
        store = FakeUserStore()
        with self.assertRaises(UserServiceError):
            create_user(store, "ADMIN", "a", "StrongPass123", role="STUDENT")

    def test_unknown_role_rejected(self):
        store = FakeUserStore()
        with self.assertRaises(UserServiceError):
            create_user(store, "ADMIN", "user2", "StrongPass123", role="HACKER")

    def test_password_never_stored_in_plaintext(self):
        store = FakeUserStore()
        user = create_user(store, "ADMIN", "user3", "StrongPass123", role="STUDENT")
        self.assertNotIn("StrongPass123", user.password_hash)


class TestAccountManagement(unittest.TestCase):
    def test_admin_can_deactivate_and_reactivate(self):
        store = FakeUserStore()
        user = create_user(store, "ADMIN", "user1", "StrongPass123", role="TEACHER")
        deactivated = deactivate_user(store, "ADMIN", user.id)
        self.assertFalse(deactivated.is_active)
        reactivated = reactivate_user(store, "ADMIN", user.id)
        self.assertTrue(reactivated.is_active)

    def test_teacher_cannot_deactivate_accounts(self):
        store = FakeUserStore()
        user = create_user(store, "ADMIN", "user1", "StrongPass123", role="STUDENT")
        with self.assertRaises(UserServiceError):
            deactivate_user(store, "TEACHER", user.id)

    def test_only_super_admin_can_change_role(self):
        store = FakeUserStore()
        user = create_user(store, "ADMIN", "user1", "StrongPass123", role="STUDENT")
        with self.assertRaises(UserServiceError):
            change_role(store, "ADMIN", user.id, "TEACHER")
        updated = change_role(store, "SUPER_ADMIN", user.id, "TEACHER")
        self.assertEqual(updated.role, "TEACHER")

    def test_reset_password_updates_hash(self):
        store = FakeUserStore()
        user = create_user(store, "ADMIN", "user1", "StrongPass123", role="STUDENT")
        old_hash = user.password_hash
        updated = reset_password(store, "ADMIN", user.id, "NewStrongerPass456")
        self.assertNotEqual(updated.password_hash, old_hash)
        self.assertTrue(auth_core.verify_password("NewStrongerPass456", updated.password_hash))

    def test_list_users_requires_management_permission(self):
        store = FakeUserStore()
        create_user(store, "ADMIN", "usr1", "StrongPass123", role="TEACHER")
        create_user(store, "ADMIN", "usr2", "StrongPass123", role="STUDENT")
        with self.assertRaises(UserServiceError):
            list_users(store, "TEACHER")
        result = list_users(store, "ADMIN", role="TEACHER")
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
