"""Token validation for humans (OIDC) and minting/validation of run-bound agent tokens."""
from __future__ import annotations

import json
import logging
import secrets
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import jwt

from app.auth.principal import Principal
from app.auth.policy import permissions_for_roles
from app.config import get_settings

logger = logging.getLogger(__name__)

AGENT_PERMISSIONS_PATH = Path(__file__).with_name("agent_permissions.json")
_LEEWAY_SECONDS = 30


class AuthError(Exception):
    """Raised for any token problem. The message is safe to return to the caller."""


@lru_cache
def agent_registry() -> dict[str, Any]:
    return json.loads(AGENT_PERMISSIONS_PATH.read_text(encoding="utf-8"))


@lru_cache
def _agent_signing_secret() -> str:
    secret = get_settings().agent_token_secret
    if secret:
        return secret
    # Per-process secret: agent tokens die with the process, which is fine because FastAPI
    # re-mints them on every Flowise call, including the resume after human approval.
    logger.warning("AGENT_TOKEN_SECRET is not set; using a per-process random secret (single worker only).")
    return secrets.token_urlsafe(48)


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True)


# ---------------------------------------------------------------------------
# Agent runtime identities
# ---------------------------------------------------------------------------
def mint_agent_token(agent_id: str, *, run_id: str, tenant_id: str, customer_id: int, ttl_seconds: int | None = None) -> str:
    registry = agent_registry()
    agent = registry["agents"].get(agent_id)
    if agent is None:
        raise ValueError(f"Unknown agent identity: {agent_id}")
    now = int(time.time())
    claims = {
        "iss": registry["token_issuer"],
        "aud": registry["token_audience"],
        "sub": f"agent:{agent_id}",
        "agent_id": agent_id,
        "run_id": run_id,
        "tenant_id": tenant_id,
        "customer_id": customer_id,
        "scope": " ".join(agent["scopes"]),
        "iat": now,
        "exp": now + (ttl_seconds or get_settings().agent_token_ttl_seconds),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(claims, _agent_signing_secret(), algorithm="HS256")


def mint_run_tokens(*, run_id: str, tenant_id: str, customer_id: int) -> dict[str, str]:
    """One token per agent identity, exposed to Flowise as $vars.agent_token_<agent_id>."""
    return {
        f"agent_token_{agent_id}": mint_agent_token(agent_id, run_id=run_id, tenant_id=tenant_id, customer_id=customer_id)
        for agent_id in agent_registry()["agents"]
    }


def _validate_agent_token(token: str) -> Principal:
    registry = agent_registry()
    try:
        claims = jwt.decode(
            token,
            _agent_signing_secret(),
            algorithms=["HS256"],
            audience=registry["token_audience"],
            issuer=registry["token_issuer"],
            leeway=_LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"Invalid agent token: {exc}") from exc
    agent_id = claims.get("agent_id")
    agent = registry["agents"].get(agent_id or "")
    if agent is None or claims.get("sub") != f"agent:{agent_id}":
        raise AuthError("Unknown agent identity")
    # Scopes come from the registry, not the token, so a revoked scope takes effect immediately.
    return Principal(
        subject=claims["sub"],
        kind="agent",
        tenant_id=str(claims["tenant_id"]),
        roles=frozenset({"ai_agent_runtime"}),
        permissions=frozenset(agent["scopes"]),
        agent_id=agent_id,
        run_id=str(claims["run_id"]),
        customer_id=int(claims["customer_id"]),
    )


# ---------------------------------------------------------------------------
# Human identities (OIDC)
# ---------------------------------------------------------------------------
def _roles_from_claims(claims: dict[str, Any]) -> set[str]:
    roles = set(claims.get("roles") or [])
    roles |= set((claims.get("realm_access") or {}).get("roles") or [])
    return {role.replace("-", "_").lower() for role in roles}


def _human_principal(claims: dict[str, Any]) -> Principal:
    settings = get_settings()
    tenant_id = claims.get(settings.oidc_tenant_claim)
    if not tenant_id:
        raise AuthError(f"Token has no {settings.oidc_tenant_claim} claim")
    roles = _roles_from_claims(claims)
    # A human token can never carry agent identity, even if someone adds the role in the IdP.
    roles.discard("ai_agent_runtime")
    return Principal(
        subject=str(claims.get("preferred_username") or claims["sub"]),
        kind="human",
        tenant_id=str(tenant_id),
        roles=frozenset(roles),
        permissions=permissions_for_roles(roles),
    )


def _validate_human_token(token: str) -> Principal:
    settings = get_settings()
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthError(f"Malformed token: {exc}") from exc
    options = {"require": ["exp", "iat", "sub", "aud", "iss"]}

    if header.get("alg") == "HS256":
        if not (settings.auth_dev_mode and settings.auth_dev_jwt_secret):
            raise AuthError("HS256 tokens are only accepted in AUTH_DEV_MODE")
        key, algorithms, issuer = settings.auth_dev_jwt_secret, ["HS256"], settings.auth_dev_issuer
    else:
        if not (settings.oidc_jwks_url and settings.oidc_issuer):
            raise AuthError("OIDC is not configured (OIDC_ISSUER / OIDC_JWKS_URL)")
        try:
            key = _jwks_client(settings.oidc_jwks_url).get_signing_key_from_jwt(token).key
        except jwt.PyJWTError as exc:
            raise AuthError(f"Signing key not found: {exc}") from exc
        algorithms, issuer = ["RS256", "ES256"], settings.oidc_issuer
    try:
        claims = jwt.decode(token, key, algorithms=algorithms, audience=settings.oidc_audience, issuer=issuer, leeway=_LEEWAY_SECONDS, options=options)
    except jwt.PyJWTError as exc:
        raise AuthError(f"Invalid token: {exc}") from exc
    return _human_principal(claims)


def principal_from_token(token: str) -> Principal:
    try:
        issuer = jwt.decode(token, options={"verify_signature": False}).get("iss")
    except jwt.PyJWTError as exc:
        raise AuthError(f"Malformed token: {exc}") from exc
    # The issuer only picks which verification applies; every path verifies the signature.
    if issuer == agent_registry()["token_issuer"]:
        return _validate_agent_token(token)
    return _validate_human_token(token)


def mint_dev_human_token(username: str, roles: list[str], tenant_id: str, ttl_seconds: int = 3600) -> str:
    settings = get_settings()
    if not (settings.auth_dev_mode and settings.auth_dev_jwt_secret):
        raise RuntimeError("Set AUTH_DEV_MODE=true and AUTH_DEV_JWT_SECRET to mint dev tokens")
    now = int(time.time())
    claims = {
        "iss": settings.auth_dev_issuer,
        "aud": settings.oidc_audience,
        "sub": f"dev|{username}",
        "preferred_username": username,
        "roles": roles,
        settings.oidc_tenant_claim: tenant_id,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(claims, settings.auth_dev_jwt_secret, algorithm="HS256")
