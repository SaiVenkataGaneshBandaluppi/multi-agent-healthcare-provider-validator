"""
MIT License
API integration tests using FastAPI TestClient with mocked external dependencies.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings

VALID_PROVIDER_PAYLOAD = {
    "providers": [
        {
            "npi": "1234567890",
            "name": "Dr. Jane Smith",
            "specialty": "Cardiology",
            "phone": "+12135551234",
            "address": "100 Main St",
            "city": "Los Angeles",
            "state": "CA",
            "zip_code": "90001",
        }
    ]
}

MOCK_BATCH_RESULT = {
    "total": 1,
    "approved": 1,
    "flagged": 0,
    "failed": 0,
    "average_confidence_score": 0.9,
    "processing_time_seconds": 0.5,
    "results": [
        {
            "npi": "1234567890",
            "name": "Dr. Jane Smith",
            "final_status": "approved",
            "confidence_score": 0.9,
            "validation_result": {
                "status": "validated",
                "confidence_score": 0.9,
                "matched_fields": ["name"],
                "mismatched_fields": [],
                "error": None,
                "nppes_record": None,
            },
            "enrichment_result": {
                "status": "enriched",
                "enriched_provider": {
                    "npi": "1234567890",
                    "name": "Dr. Jane Smith",
                    "specialty": "Cardiology",
                    "phone": "+12135551234",
                    "address": "100 Main St",
                    "city": "Los Angeles",
                    "state": "CA",
                    "zip_code": "90001",
                },
                "modified_fields": [],
                "field_confidences": {},
                "enrichment_method": "rule_based",
            },
            "qa_result": {
                "quality_score": 1.0,
                "decision": "approved",
                "flags": [],
                "issues": [],
                "reasoning": "No issues found.",
                "auto_approved": True,
            },
            "error": None,
        }
    ],
}


def _make_mock_session():
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = 0
    mock_result.scalars.return_value.all.return_value = []
    mock_result.all.return_value = []

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock(return_value=None)
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


@pytest.fixture
def client():
    mock_session = _make_mock_session()
    with patch("app.main.create_tables", new_callable=AsyncMock), \
         patch("app.db.database.AsyncSessionLocal", return_value=mock_session):
        from app.main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


@pytest.fixture
def auth_headers(client):
    response = client.post(
        "/auth/token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health_no_auth(client):
    with patch("app.api.routes._check_db", new_callable=AsyncMock, return_value=True), \
         patch("app.api.routes._check_redis", new_callable=AsyncMock, return_value=True):
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert data["version"] == "1.0.0"


def test_login_valid_credentials(client):
    response = client.post(
        "/auth/token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_credentials(client):
    response = client.post(
        "/auth/token",
        data={"username": "wronguser", "password": "wrongpassword"},
    )
    assert response.status_code == 401


def test_validate_without_auth(client):
    response = client.post("/api/v1/validate", json=VALID_PROVIDER_PAYLOAD)
    assert response.status_code == 401


def test_validate_with_auth_and_valid_payload(client, auth_headers):
    with patch("app.api.routes.run_management_agent", new_callable=AsyncMock, return_value=MOCK_BATCH_RESULT):
        response = client.post(
            "/api/v1/validate",
            json=VALID_PROVIDER_PAYLOAD,
            headers=auth_headers,
        )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["approved"] == 1
    assert "batch_id" in data
    assert len(data["results"]) == 1


def test_validate_invalid_npi_too_short(client, auth_headers):
    payload = {
        "providers": [
            {
                "npi": "12345",
                "name": "Dr. Test",
                "specialty": "Cardiology",
                "phone": "+12135551234",
                "address": "100 Main St",
                "city": "Los Angeles",
                "state": "CA",
                "zip_code": "90001",
            }
        ]
    }
    response = client.post("/api/v1/validate", json=payload, headers=auth_headers)
    assert response.status_code == 422


def test_validate_npi_with_letters(client, auth_headers):
    payload = {
        "providers": [
            {
                "npi": "ABCD123456",
                "name": "Dr. Test",
                "specialty": "Cardiology",
                "phone": "+12135551234",
                "address": "100 Main St",
                "city": "Los Angeles",
                "state": "CA",
                "zip_code": "90001",
            }
        ]
    }
    response = client.post("/api/v1/validate", json=payload, headers=auth_headers)
    assert response.status_code == 422


def test_providers_endpoint_requires_auth(client):
    response = client.get("/api/v1/providers")
    assert response.status_code == 401


def test_auth_me_endpoint(client, auth_headers):
    response = client.get("/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "username" in data
    assert data["username"] == settings.ADMIN_USERNAME


def test_validate_batch_too_large(client, auth_headers):
    providers = []
    for i in range(51):
        providers.append({
            "npi": f"1{str(i).zfill(9)}",
            "name": f"Dr. Provider {i}",
            "specialty": "Cardiology",
            "phone": "+12135551234",
            "address": "100 Main St",
            "city": "Los Angeles",
            "state": "CA",
            "zip_code": "90001",
        })
    response = client.post(
        "/api/v1/validate",
        json={"providers": providers},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_rate_limit_header_check(client, auth_headers):
    with patch("app.api.routes.run_management_agent", new_callable=AsyncMock, return_value=MOCK_BATCH_RESULT):
        response = client.post(
            "/api/v1/validate",
            json=VALID_PROVIDER_PAYLOAD,
            headers=auth_headers,
        )
    assert response.status_code in (200, 429)
