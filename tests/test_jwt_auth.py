# -*- coding: utf-8 -*-
"""Unit tests for JWT authentication module."""

import os
import time
import unittest

# Set test JWT secret before import
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-unit-tests-12345678"


class TestJWTAuth(unittest.TestCase):
    """Test JWT token generation and verification."""

    def setUp(self):
        """Reset module state for each test."""
        import importlib
        import src.jwt_auth as jwt_mod
        importlib.reload(jwt_mod)
        self.jwt = jwt_mod

    def test_create_access_token(self):
        """Access token should be decodable and contain correct claims."""
        token = self.jwt.create_access_token(user_id=42, role="user")
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 20)

        payload = self.jwt.verify_token(token, expected_type="access")
        self.assertIsNotNone(payload)
        self.assertEqual(payload["sub"], "42")
        self.assertEqual(payload["role"], "user")
        self.assertEqual(payload["type"], "access")

    def test_create_refresh_token(self):
        """Refresh token should have type=refresh and be verifiable."""
        token = self.jwt.create_refresh_token(user_id=7)
        payload = self.jwt.verify_token(token, expected_type="refresh")
        self.assertIsNotNone(payload)
        self.assertEqual(payload["sub"], "7")
        self.assertEqual(payload["type"], "refresh")

    def test_access_token_wrong_type(self):
        """Verifying access token as refresh should fail."""
        token = self.jwt.create_access_token(user_id=1, role="admin")
        payload = self.jwt.verify_token(token, expected_type="refresh")
        self.assertIsNone(payload)

    def test_refresh_token_wrong_type(self):
        """Verifying refresh token as access should fail."""
        token = self.jwt.create_refresh_token(user_id=1)
        payload = self.jwt.verify_token(token, expected_type="access")
        self.assertIsNone(payload)

    def test_invalid_token_returns_none(self):
        """Completely invalid token should return None."""
        payload = self.jwt.verify_token("not.a.valid.jwt.token")
        self.assertIsNone(payload)

    def test_empty_token_returns_none(self):
        """Empty string token should return None."""
        payload = self.jwt.verify_token("")
        self.assertIsNone(payload)

    def test_tampered_token_returns_none(self):
        """Tampered token should fail verification."""
        token = self.jwt.create_access_token(user_id=1, role="user")
        tampered = token[:-5] + "XXXXX"
        payload = self.jwt.verify_token(tampered)
        self.assertIsNone(payload)

    def test_admin_role_preserved(self):
        """Admin role should be correctly stored and retrieved."""
        token = self.jwt.create_access_token(user_id=99, role="super_admin")
        payload = self.jwt.verify_token(token)
        self.assertEqual(payload["role"], "super_admin")

    def test_missing_secret_auto_generates(self):
        """When JWT_SECRET_KEY is empty, should auto-generate (warning)."""
        old_key = os.environ.get("JWT_SECRET_KEY", "")
        try:
            os.environ["JWT_SECRET_KEY"] = ""
            import importlib
            import src.jwt_auth as jwt_mod
            importlib.reload(jwt_mod)
            # Should auto-generate and work
            token = jwt_mod.create_access_token(user_id=1, role="user")
            payload = jwt_mod.verify_token(token)
            self.assertIsNotNone(payload)
        finally:
            os.environ["JWT_SECRET_KEY"] = old_key


if __name__ == "__main__":
    unittest.main()
