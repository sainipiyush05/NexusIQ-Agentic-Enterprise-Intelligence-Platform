"""Trusted caller identity, JWT token issuance, verification, and role/tenant scoping."""
import os
import time
from dataclasses import dataclass
from typing import Sequence

DEFAULT_DEV_SECRET = "nexusiq-dev-insecure-secret-key-38491028471"
ALGORITHM = "HS256"
VALID_ROLES = frozenset({"admin", "analyst", "viewer"})


class AuthError(ValueError):
    pass


class TokenExpiredError(AuthError):
    pass


class InvalidTokenError(AuthError):
    pass


class ForbiddenError(AuthError):
    pass


@dataclass(frozen=True)
class UserIdentity:
    user_id: str
    tenant_id: str
    roles: tuple[str, ...]
    scopes: tuple[str, ...] = ()

    def has_role(self, *required_roles: str) -> bool:
        return any(role in self.roles for role in required_roles)

    def assert_role(self, *required_roles: str) -> None:
        if not self.has_role(*required_roles):
            raise ForbiddenError(f"Operation requires one of roles: {list(required_roles)}; caller has {list(self.roles)}")

    def assert_tenant(self, expected_tenant: str) -> None:
        if self.tenant_id != expected_tenant:
            raise ForbiddenError(f"Cross-tenant access rejected: user belongs to '{self.tenant_id}', target is '{expected_tenant}'")


def _get_secret() -> str:
    return os.environ.get("NEXUSIQ_SECRET_KEY", DEFAULT_DEV_SECRET)


def issue_token(
    user_id: str,
    tenant_id: str,
    roles: Sequence[str] | str = ("analyst",),
    scopes: Sequence[str] = (),
    expires_in_seconds: int = 3600,
) -> str:
    import jwt

    if isinstance(roles, str):
        roles = (roles,)
    roles_list = list(roles)
    if not user_id or not isinstance(user_id, str):
        raise ValueError("user_id must be a nonempty string")
    if not tenant_id or not isinstance(tenant_id, str):
        raise ValueError("tenant_id must be a nonempty string")
    for r in roles_list:
        if r not in VALID_ROLES:
            raise ValueError(f"Invalid role: {r}. Must be one of {sorted(VALID_ROLES)}")

    now = int(time.time())
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "roles": roles_list,
        "scopes": list(scopes),
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    return jwt.encode(payload, _get_secret(), algorithm=ALGORITHM)


def verify_token(token: str) -> UserIdentity:
    import jwt

    if not isinstance(token, str) or not token.strip():
        raise InvalidTokenError("Missing or empty authentication token")

    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Authentication token has expired") from exc
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(f"Invalid authentication token: {exc}") from exc

    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    roles = payload.get("roles", [])
    scopes = payload.get("scopes", [])

    if not user_id or not tenant_id or not isinstance(roles, list):
        raise InvalidTokenError("Token payload missing required identity claims")

    return UserIdentity(
        user_id=str(user_id),
        tenant_id=str(tenant_id),
        roles=tuple(str(r) for r in roles),
        scopes=tuple(str(s) for s in scopes),
    )


def create_demo_identity(role: str = "analyst", tenant_id: str = "atlascloud") -> UserIdentity:
    return UserIdentity(
        user_id="demo-user-001",
        tenant_id=tenant_id,
        roles=(role,),
        scopes=("read", "query", "analytics"),
    )
