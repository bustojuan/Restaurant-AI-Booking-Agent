import secrets
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import DomainError

bearer = HTTPBearer(auto_error=False)


def authenticate(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> None:
    expected = request.app.state.settings.local_api_token.get_secret_value()
    if credentials is None or not secrets.compare_digest(credentials.credentials.encode(), expected.encode()):
        raise DomainError("unauthorized", "Valid local bearer token required", 401)


def expected_version(
    if_match: Annotated[str | None, Header(description='Resource version, e.g. "3"')] = None,
) -> int:
    if if_match is None:
        raise DomainError("version_required", "Send the current resource version in If-Match", 428)
    value = if_match
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    if not value.isascii() or not value.isdecimal() or len(value) > 12 or int(value) < 1:
        raise DomainError("invalid_version", "If-Match must contain a positive integer version", 422)
    return int(value)


Version = Annotated[int, Depends(expected_version)]
