from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.settings import Settings

security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    roles: set[str]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def _developer_context() -> AuthContext:
    return AuthContext(
        user_id="dev-local",
        roles={"admin", "recruiter", "employer", "service"},
    )


def get_auth_context(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> AuthContext:
    settings = get_settings(request)
    if not settings.auth_enabled:
        return _developer_context()

    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid auth token",
        ) from exc

    subject = payload.get("sub")
    roles = payload.get("roles", [])
    if not isinstance(subject, str) or not subject.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token missing subject",
        )
    if not isinstance(roles, list):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token roles must be a list",
        )
    role_set = {str(role).strip() for role in roles if str(role).strip()}
    if not role_set:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="token has no roles",
        )
    return AuthContext(user_id=subject.strip(), roles=role_set)


def require_roles(*required_roles: str) -> Callable[[AuthContext], AuthContext]:
    required = {role.strip() for role in required_roles if role.strip()}

    def dependency(context: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if required and context.roles.isdisjoint(required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"insufficient role. required any of: {sorted(required)}",
            )
        return context

    return dependency
