"""Unit/integration test: the one endpoint with zero auth and zero logic.

If this fails, the problem is infrastructure (the app can't even start),
never business logic -- see docs/milestones/01-repo-health.md.
"""


def test_health_returns_ok_without_auth(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
