"""Mint a dev-only human token for local demos without Keycloak.

    AUTH_DEV_MODE=true AUTH_DEV_JWT_SECRET=... python -m app.auth.dev_tokens --user alice --role loan_officer
"""
from __future__ import annotations

import argparse

from app.auth.tokens import mint_dev_human_token
from app.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", required=True)
    parser.add_argument("--role", action="append", required=True, help="repeatable, e.g. --role loan_officer")
    parser.add_argument("--tenant", default=get_settings().default_tenant_id)
    parser.add_argument("--ttl", type=int, default=3600)
    args = parser.parse_args()
    print(mint_dev_human_token(args.user, args.role, args.tenant, args.ttl))


if __name__ == "__main__":
    main()
