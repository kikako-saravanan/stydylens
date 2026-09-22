"""Unit/integration test: credit-consuming endpoints must reject
unauthenticated or wrong-credential requests, at the API layer -- not
just "the frontend has a login screen." See docs/milestones/06 and
docs/milestones/11 for why this is enforced server-side.
"""

import base64

from tests.conftest import AUTH_USERNAME


def test_upload_requires_auth(client):
    response = client.post("/api/upload")
    assert response.status_code == 401


def test_query_rejects_wrong_credentials(client):
    bad_token = base64.b64encode(b"wrong:wrong").decode()
    response = client.post(
        "/api/query",
        json={"question": "anything"},
        headers={"Authorization": f"Basic {bad_token}"},
    )
    assert response.status_code == 401
    # The rejection message states why access is restricted -- not just
    # a bare 401 with no explanation of what to do about it.
    assert "administrator" in response.json()["detail"].lower()


def test_me_accepts_correct_credentials(client, auth_headers):
    response = client.get("/api/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"username": AUTH_USERNAME}


def test_health_does_not_require_auth(client):
    # /health is deliberately exempt -- deployment platforms poll it
    # without credentials (docs/milestones/01-repo-health.md).
    response = client.get("/health")
    assert response.status_code == 200
