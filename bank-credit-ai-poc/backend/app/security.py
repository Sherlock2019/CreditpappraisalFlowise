# POC security placeholder. Do not use this as-is for production.
#
# TODO: integrate Cognito / Keycloak / Azure AD.
# TODO: add RBAC for loan officers, analysts, approvers, and admins.
# TODO: add customer-level permissions and tenant isolation.
# TODO: add PII masking before model calls and logs.
# TODO: add audit retention policy and immutable audit storage.


def get_current_user() -> dict[str, str]:
    return {"user_id": "local-poc-user", "role": "loan_officer"}
