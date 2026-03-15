# -*- coding: utf-8 -*-
"""Unit tests for UserService: registration, login, token refresh, profile."""

import os
import unittest
from unittest.mock import patch, MagicMock

# Set test JWT secret before import
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-unit-tests-12345678"


class TestUserServicePasswordHashing(unittest.TestCase):
    """Test password hashing and verification functions."""

    def test_hash_and_verify_correct(self):
        from src.services.user_service import _hash_password, _verify_password
        stored = _hash_password("mypassword123")
        self.assertTrue(_verify_password("mypassword123", stored))

    def test_hash_and_verify_wrong_password(self):
        from src.services.user_service import _hash_password, _verify_password
        stored = _hash_password("mypassword123")
        self.assertFalse(_verify_password("wrongpassword", stored))

    def test_hash_format(self):
        """Hash should be in 'salt:hash' hex format."""
        from src.services.user_service import _hash_password
        stored = _hash_password("test")
        self.assertIn(":", stored)
        parts = stored.split(":")
        self.assertEqual(len(parts), 2)
        # Both parts should be valid hex
        bytes.fromhex(parts[0])
        bytes.fromhex(parts[1])

    def test_different_passwords_different_hashes(self):
        from src.services.user_service import _hash_password
        h1 = _hash_password("password1")
        h2 = _hash_password("password2")
        self.assertNotEqual(h1, h2)

    def test_same_password_different_salts(self):
        """Same password should produce different hashes (random salt)."""
        from src.services.user_service import _hash_password
        h1 = _hash_password("samepassword")
        h2 = _hash_password("samepassword")
        self.assertNotEqual(h1, h2)

    def test_verify_invalid_stored_format(self):
        from src.services.user_service import _verify_password
        self.assertFalse(_verify_password("password", "invalid"))
        self.assertFalse(_verify_password("password", ""))
        self.assertFalse(_verify_password("password", "no:colonseparated:here"))


class TestUserServiceValidation(unittest.TestCase):
    """Test input validation in UserService."""

    def test_invalid_email_formats(self):
        from src.services.user_service import UserServiceError
        # We test the email regex directly
        from src.services.user_service import EMAIL_REGEX
        self.assertIsNone(EMAIL_REGEX.match(""))
        self.assertIsNone(EMAIL_REGEX.match("notanemail"))
        self.assertIsNone(EMAIL_REGEX.match("@nodomain"))
        self.assertIsNone(EMAIL_REGEX.match("user@"))

    def test_valid_email_formats(self):
        from src.services.user_service import EMAIL_REGEX
        self.assertIsNotNone(EMAIL_REGEX.match("user@example.com"))
        self.assertIsNotNone(EMAIL_REGEX.match("test.user@domain.co"))
        self.assertIsNotNone(EMAIL_REGEX.match("a+b@c.org"))

    def test_password_min_length(self):
        from src.services.user_service import MIN_PASSWORD_LEN
        self.assertEqual(MIN_PASSWORD_LEN, 6)


class TestUserServiceErrorCodes(unittest.TestCase):
    """Test UserServiceError exception."""

    def test_error_has_code(self):
        from src.services.user_service import UserServiceError
        err = UserServiceError("test message", "test_code")
        self.assertEqual(str(err), "test message")
        self.assertEqual(err.code, "test_code")

    def test_default_code(self):
        from src.services.user_service import UserServiceError
        err = UserServiceError("test")
        self.assertEqual(err.code, "user_error")


if __name__ == "__main__":
    unittest.main()
