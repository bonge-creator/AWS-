"""Single source of truth for Postgres enum types (created once, by migration)."""

from sqlalchemy.dialects.postgresql import ENUM


def _enum(name: str, *values: str) -> ENUM:
    # create_type=False: the migration owns CREATE TYPE, so models that share
    # a type (users.role / document_permissions.grantee_role) never double-create it.
    return ENUM(*values, name=name, create_type=False)


USER_ROLES = ("admin", "analyst", "viewer")
DOC_TYPES = ("contract", "lease", "invoice", "report", "policy", "nda", "other")
DOC_STATUSES = ("uploaded", "processing", "ready", "failed")
JOB_STATUSES = ("queued", "running", "succeeded", "failed")
PERMISSIONS = ("view", "download", "manage")
GRANTEE_TYPES = ("user", "role")
MESSAGE_ROLES = ("user", "assistant")

user_role = lambda: _enum("user_role", *USER_ROLES)  # noqa: E731
doc_type_enum = lambda: _enum("doc_type_enum", *DOC_TYPES)  # noqa: E731
document_status = lambda: _enum("document_status", *DOC_STATUSES)  # noqa: E731
job_status = lambda: _enum("job_status", *JOB_STATUSES)  # noqa: E731
permission_enum = lambda: _enum("permission_enum", *PERMISSIONS)  # noqa: E731
grantee_type_enum = lambda: _enum("grantee_type_enum", *GRANTEE_TYPES)  # noqa: E731
message_role = lambda: _enum("message_role", *MESSAGE_ROLES)  # noqa: E731
