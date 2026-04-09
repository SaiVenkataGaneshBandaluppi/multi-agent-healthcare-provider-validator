"""
MIT License
LangGraph workflow integration tests with mocked agent calls.
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.graph.workflow import run_validation_workflow

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

MOCK_VALIDATION_SUCCESS = {
    "status": "validated",
    "confidence_score": 0.9,
    "matched_fields": ["name", "state"],
    "mismatched_fields": [],
    "error": None,
    "nppes_record": {"name": "jane smith", "state": "CA", "zip_code": "90001", "taxonomies": []},
}

MOCK_VALIDATION_FAILURE = {
    "status": "failed",
    "confidence_score": 0.0,
    "matched_fields": [],
    "mismatched_fields": ["npi_not_found"],
    "error": "NPI not found in registry",
    "nppes_record": None,
}

MOCK_ENRICHMENT = {
    "status": "enriched",
    "enriched_provider": VALID_PROVIDER,
    "modified_fields": ["phone"],
    "field_confidences": {"phone": 0.95},
    "enrichment_method": "rule_based",
}

MOCK_QA_APPROVED = {
    "quality_score": 1.0,
    "decision": "approved",
    "flags": [],
    "issues": [],
    "reasoning": "No issues found.",
    "auto_approved": True,
}

MOCK_QA_FLAGGED = {
    "quality_score": 0.5,
    "decision": "flagged",
    "flags": ["missing_fields"],
    "issues": ["Missing required fields: phone"],
    "reasoning": "Quality score 0.50. Issues found: Missing required fields: phone",
    "auto_approved": False,
}


@pytest.mark.asyncio
async def test_workflow_successful_validation():
    with patch("app.graph.workflow.run_validation_agent", new_callable=AsyncMock, return_value=MOCK_VALIDATION_SUCCESS), \
         patch("app.graph.workflow.run_enrichment_agent", new_callable=AsyncMock, return_value=MOCK_ENRICHMENT), \
         patch("app.graph.workflow.run_qa_agent", new_callable=AsyncMock, return_value=MOCK_QA_APPROVED):
        final_state = await run_validation_workflow(VALID_PROVIDER)

    assert "status" in final_state
    assert final_state["status"] == "approved"
    assert final_state["validation_result"] is not None
    assert final_state["enrichment_result"] is not None
    assert final_state["qa_result"] is not None


@pytest.mark.asyncio
async def test_workflow_failed_validation_skips_enrichment():
    enrichment_mock = AsyncMock()
    qa_mock = AsyncMock()

    with patch("app.graph.workflow.run_validation_agent", new_callable=AsyncMock, return_value=MOCK_VALIDATION_FAILURE), \
         patch("app.graph.workflow.run_enrichment_agent", enrichment_mock), \
         patch("app.graph.workflow.run_qa_agent", qa_mock):
        final_state = await run_validation_workflow(VALID_PROVIDER)

    assert final_state["status"] == "failed"
    enrichment_mock.assert_not_called()
    qa_mock.assert_not_called()


@pytest.mark.asyncio
async def test_workflow_flagged_decision():
    with patch("app.graph.workflow.run_validation_agent", new_callable=AsyncMock, return_value=MOCK_VALIDATION_SUCCESS), \
         patch("app.graph.workflow.run_enrichment_agent", new_callable=AsyncMock, return_value=MOCK_ENRICHMENT), \
         patch("app.graph.workflow.run_qa_agent", new_callable=AsyncMock, return_value=MOCK_QA_FLAGGED):
        final_state = await run_validation_workflow(VALID_PROVIDER)

    assert final_state["status"] == "flagged"
    assert final_state["qa_result"]["decision"] == "flagged"


@pytest.mark.asyncio
async def test_workflow_state_has_required_fields():
    with patch("app.graph.workflow.run_validation_agent", new_callable=AsyncMock, return_value=MOCK_VALIDATION_SUCCESS), \
         patch("app.graph.workflow.run_enrichment_agent", new_callable=AsyncMock, return_value=MOCK_ENRICHMENT), \
         patch("app.graph.workflow.run_qa_agent", new_callable=AsyncMock, return_value=MOCK_QA_APPROVED):
        final_state = await run_validation_workflow(VALID_PROVIDER)

    required_fields = {"provider", "validation_result", "enrichment_result", "qa_result", "status"}
    for field in required_fields:
        assert field in final_state, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_workflow_handles_validation_agent_exception():
    with patch("app.graph.workflow.run_validation_agent", new_callable=AsyncMock, side_effect=RuntimeError("NPPES down")):
        final_state = await run_validation_workflow(VALID_PROVIDER)

    assert final_state["status"] == "failed"
    assert final_state.get("error") is not None
