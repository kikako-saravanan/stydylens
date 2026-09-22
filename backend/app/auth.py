import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

ACCESS_DENIED_MESSAGE = (
    "Invalid credentials. This app is access-restricted to control LLM API "
    "costs. Email the administrator for access."
)


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """Gate access to credit-consuming endpoints behind a shared username/password.

    Compares with secrets.compare_digest, not `==`. A plain `==` on strings
    short-circuits at the first mismatched character, so how long a rejection
    takes leaks how many leading characters were correct — a real timing
    side-channel an attacker could use to guess credentials one character at
    a time. compare_digest always takes the same time regardless of where
    the mismatch is, closing that channel.
    """
    expected_username = os.getenv("AUTH_USERNAME", "studylens")
    expected_password = os.getenv("AUTH_PASSWORD", "studylens-demo-2026")

    username_ok = secrets.compare_digest(credentials.username, expected_username)
    password_ok = secrets.compare_digest(credentials.password, expected_password)

    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ACCESS_DENIED_MESSAGE,
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
