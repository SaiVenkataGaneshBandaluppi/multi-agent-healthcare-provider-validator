"""
MIT License
Management agent: orchestrates validation workflow across a batch of providers.
"""
import asyncio
import logging
import time
from typing import Optional

from app.agents.enrichment_agent import run_enrichment_agent
from app.agents.qa_agent import run_qa_agent
from app.agents.validation_agent import run_validation_agent
from app.services.groq_client import GroqClient, get_groq_client
from app.services.nppes_client import NPPESClient, get_nppes_client

logger = logging.getLogger(__name__)


async def process_single_provider(
    provider: dict,
    nppes_client: NPPESClient,
    groq_client: Optional[GroqClient],
) -> dict:
    result = {
        "npi": provider.get("npi"),
        "name": provider.get("name"),
        "validation_result": None,
        "enrichment_result": None,
        "qa_result": None,
        "final_status": "failed",
        "confidence_score": 0.0,
        "error": None,
    }

    try:
        validation_result = await run_validation_agent(provider, nppes_client)
        result["validation_result"] = validation_result

        if validation_result["status"] == "failed":
            result["final_status"] = "failed"
            result["error"] = validation_result.get("error")
            result["confidence_score"] = 0.0
            return result

        enrichment_result = await run_enrichment_agent(
            provider, groq_client=groq_client
        )
        result["enrichment_result"] = enrichment_result
        enriched_provider = enrichment_result.get("enriched_provider", provider)

        qa_result = await run_qa_agent(enriched_provider)
        result["qa_result"] = qa_result

        if qa_result["decision"] == "approved":
            result["final_status"] = "approved"
        else:
            result["final_status"] = "flagged"

        val_score = validation_result.get("confidence_score", 0.0)
        qa_score = qa_result.get("quality_score", 0.0)
        result["confidence_score"] = round((val_score + qa_score) / 2, 2)

    except Exception as exc:
        logger.error(
            "Unexpected error processing provider NPI %s: %s",
            provider.get("npi", "unknown"),
            exc,
        )
        result["final_status"] = "failed"
        result["error"] = "Internal processing error"

    return result


async def run_management_agent(providers: list[dict]) -> dict:
    start_time = time.time()

    nppes_client = await get_nppes_client()
    groq_client = get_groq_client()

    tasks = [
        process_single_provider(provider, nppes_client, groq_client)
        for provider in providers
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    total = len(results)
    approved = sum(1 for r in results if r["final_status"] == "approved")
    flagged = sum(1 for r in results if r["final_status"] == "flagged")
    failed = sum(1 for r in results if r["final_status"] == "failed")
    scores = [r["confidence_score"] for r in results if r["confidence_score"] > 0]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0

    processing_time = round(time.time() - start_time, 2)

    return {
        "total": total,
        "approved": approved,
        "flagged": flagged,
        "failed": failed,
        "average_confidence_score": avg_score,
        "processing_time_seconds": processing_time,
        "results": results,
    }
