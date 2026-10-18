"""FastAPI dependencies. Every /api/v1 route declares one of these; there is no unauthenticated v1 route."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status

from app.auth.policy import HUMAN_ONLY_PERMISSIONS
from app.auth.principal import Principal
from app.auth.tokens import AuthError, principal_from_token
from app.config import get_settings


def _bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message, headers={"WWW-Authenticate": "Bearer"})


def get_principal(request: Request) -> Principal:
    token = _bearer(request)
    if token is None:
        raise _unauthorized("Bearer token required")
    try:
        principal = principal_from_token(token)
    except AuthError as exc:
        raise _unauthorized(str(exc)) from exc
    request.state.principal = principal
    return principal


def require_permission(permission: str) -> Callable[[Principal], Principal]:
    """Human route guard. Agents are rejected for human-only permissions whatever their token says."""

    def guard(principal: Principal = Depends(get_principal)) -> Principal:
        if permission in HUMAN_ONLY_PERMISSIONS and not principal.is_human:
            raise HTTPException(status_code=403, detail=f"{permission} requires an authenticated human")
        if permission not in principal.permissions:
            raise HTTPException(status_code=403, detail=f"Missing permission {permission}")
        return principal

    return guard


def require_agent() -> Callable[[Principal], Principal]:
    def guard(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.is_agent:
            raise HTTPException(status_code=403, detail="Tool endpoints accept agent runtime identities only")
        return principal

    return guard


def require_scope(principal: Principal, scope: str) -> None:
    if scope not in principal.permissions:
        raise HTTPException(status_code=403, detail=f"Agent {principal.agent_id} lacks scope {scope}")


def legacy_principal(request: Request) -> Principal:
    """For unversioned LISA/Streamlit routes: anonymous dev principal unless LEGACY_AUTH_MODE=required.

    A presented token is always validated, so an agent token can never pass as an anonymous human.
    """
    settings = get_settings()
    if _bearer(request) is not None or settings.legacy_auth_mode == "required":
        return get_principal(request)
    return Principal(subject="local-dev-anonymous", kind="anonymous", tenant_id=settings.default_tenant_id)
