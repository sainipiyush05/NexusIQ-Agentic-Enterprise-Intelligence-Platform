"""Unit tests for caller identity, JWT issuance, verification, and role/tenant scoping."""
import importlib.util
import time
import unittest

from nexusiq.auth import (
    ForbiddenError,
    InvalidTokenError,
    TokenExpiredError,
    UserIdentity,
    create_demo_identity,
    issue_token,
    verify_token,
)


@unittest.skipUnless(importlib.util.find_spec('jwt'), 'Install pyjwt for auth tests')
class TestAuth(unittest.TestCase):
    def test_issue_and_verify_token(self):
        token = issue_token(user_id="user-123", tenant_id="atlascloud", roles=["analyst", "viewer"])
        identity = verify_token(token)
        self.assertEqual(identity.user_id, "user-123")
        self.assertEqual(identity.tenant_id, "atlascloud")
        self.assertEqual(identity.roles, ("analyst", "viewer"))
        self.assertTrue(identity.has_role("analyst"))
        self.assertTrue(identity.has_role("viewer"))
        self.assertFalse(identity.has_role("admin"))

    def test_expired_token_rejected(self):
        token = issue_token(user_id="user-123", tenant_id="atlascloud", roles=["analyst"], expires_in_seconds=-10)
        with self.assertRaises(TokenExpiredError):
            verify_token(token)

    def test_tampered_token_rejected(self):
        token = issue_token(user_id="user-123", tenant_id="atlascloud", roles=["analyst"])
        tampered = token[:-5] + "abcde"
        with self.assertRaises(InvalidTokenError):
            verify_token(tampered)

    def test_empty_or_malformed_token_rejected(self):
        with self.assertRaises(InvalidTokenError):
            verify_token("")
        with self.assertRaises(InvalidTokenError):
            verify_token("not-a-jwt")

    def test_invalid_role_rejected_at_issue(self):
        with self.assertRaises(ValueError):
            issue_token(user_id="user-123", tenant_id="atlascloud", roles=["superadmin"])

    def test_empty_user_or_tenant_rejected(self):
        with self.assertRaises(ValueError):
            issue_token(user_id="", tenant_id="atlascloud", roles=["analyst"])
        with self.assertRaises(ValueError):
            issue_token(user_id="u1", tenant_id="", roles=["analyst"])

    def test_role_assertion(self):
        identity = UserIdentity(user_id="u1", tenant_id="atlascloud", roles=("viewer",))
        identity.assert_role("viewer")
        with self.assertRaises(ForbiddenError):
            identity.assert_role("admin", "analyst")

    def test_tenant_assertion(self):
        identity = UserIdentity(user_id="u1", tenant_id="tenant_a", roles=("analyst",))
        identity.assert_tenant("tenant_a")
        with self.assertRaises(ForbiddenError):
            identity.assert_tenant("atlascloud")

    def test_demo_identity(self):
        demo = create_demo_identity()
        self.assertEqual(demo.tenant_id, "atlascloud")
        self.assertEqual(demo.roles, ("analyst",))
        self.assertTrue(demo.has_role("analyst"))


if __name__ == "__main__":
    unittest.main()
