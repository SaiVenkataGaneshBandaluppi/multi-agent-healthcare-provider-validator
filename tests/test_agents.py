"""
MIT License
Unit tests for individual agents with mocked external dependencies.
"""
import pytest

from app.agents.enrichment_agent import run_enrichment_agent
from app.agents.qa_agent import run_qa_agent
from app.agents.validation_agent import run_validation_agent

VALID_PROVIDER = {
    "npi": "1234567890",
    "name": "Dr. Jane Smith",
    "specialty": "Cardiology",
    "phone": "+12135551234",
    "address": "100 Main St",
    "city": "Los Angeles",
    "state": "CA",
    "zip_code": "90001",
}

MOCK_NPPES_RECORD = {
    "basic": {
        "first_name": "Jane",
        "last_name": "Smith",
    },
    "addresses": [
        {
            "address_purpose": "LOCATION",
            "state": "CA",
            "postal_code": "900010000",
        }
    ],
    "taxonomies": [
        {"code": "207RC0000X", "primary": True}
    ],
}


class MockNPPESClient:
    async def lookup_npi(self, npi: str) -> dict:
        return MOCK_NPPES_RECORD


class MockGroqClient:
    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        return """{"npi": "1234567890", "name": "Dr. Jane Smith", "specialty": "Cardiology", "phone": "+12135551234", "address": "100 Main St", "city": "Los Angeles", "state": "CA", "zip_code": "90001"}"""


@pytest.mark.asyncio
async def test_validation_agent_valid_npi():
    client = MockNPPESClient()
    result = await run_validation_agent(VALID_PROVIDER, nppes_client=client)
    assert result["status"] == "validated"
    assert result["confidence_score"] >= 0.0
    assert "name" in result["matched_fields"] or "state" in result["matched_fields"]


@pytest.mark.asyncio
async def test_validation_agent_invalid_npi_format():
    bad_provider = dict(VALID_PROVIDER, npi="123ABC")
    result = await run_validation_agent(bad_provider, nppes_client=MockNPPESClient())
    assert result["status"] == "failed"
    assert "npi_format" in result["mismatched_fields"]


@pytest.mark.asyncio
async def test_validation_agent_npi_not_found():
    from app.services.nppes_client import NPPESNotFoundError

    class NotFoundClient:
        async def lookup_npi(self, npi: str) -> dict:
            raise NPPESNotFoundError("not found")

    result = await run_validation_agent(VALID_PROVIDER, nppes_client=NotFoundClient())
    assert result["status"] == "failed"
    assert "npi_not_found" in result["mismatched_fields"]


@pytest.mark.asyncio
async def test_enrichment_agent_with_groq():
    groq = MockGroqClient()
    result = await run_enrichment_agent(VALID_PROVIDER, groq_client=groq)
    assert result["status"] == "enriched"
    assert "enriched_provider" in result
    assert result["enrichment_method"] == "groq"


@pytest.mark.asyncio
async def test_enrichment_agent_rule_based():
    provider = dict(VALID_PROVIDER, phone="2135551234")
    result = await run_enrichment_agent(provider, groq_client=None)
    assert result["status"] == "enriched"
    assert result["enrichment_method"] == "rule_based"
    assert result["enriched_provider"]["phone"] == "+12135551234"


@pytest.mark.asyncio
async def test_enrichment_agent_specialty_normalization():
    provider = dict(VALID_PROVIDER, specialty="cardiology")
    result = await run_enrichment_agent(provider, groq_client=None)
    assert result["enriched_provider"]["specialty"] == "Cardiology"


@pytest.mark.asyncio
async def test_qa_agent_approved():
    result = await run_qa_agent(VALID_PROVIDER)
    assert "quality_score" in result
    assert "decision" in result
    assert result["decision"] in ("approved", "flagged")
    assert 0.0 <= result["quality_score"] <= 1.0


@pytest.mark.asyncio
async def test_qa_agent_missing_fields_flagged():
    incomplete = {
        "npi": "1234567890",
        "name": "Dr. Test",
        "specialty": "",
        "phone": "",
        "address": "",
        "city": "",
        "state": "CA",
        "zip_code": "",
    }
    result = await run_qa_agent(incomplete)
    assert result["decision"] == "flagged"
    assert "missing_fields" in result["flags"]


@pytest.mark.asyncio
async def test_qa_agent_zip_state_mismatch():
    mismatch = dict(VALID_PROVIDER, state="TX", zip_code="90001")
    result = await run_qa_agent(mismatch)
    assert "zip_state_mismatch" in result["flags"]


@pytest.mark.asyncio
async def test_qa_agent_phone_state_mismatch():
    mismatch = dict(VALID_PROVIDER, state="TX", phone="+12125551234")
    result = await run_qa_agent(mismatch)
    assert "phone_state_mismatch" in result["flags"]
