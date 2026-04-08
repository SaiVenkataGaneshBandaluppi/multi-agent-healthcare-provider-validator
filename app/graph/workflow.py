"""
MIT License
LangGraph state machine orchestrating the four-agent validation pipeline.
"""
import logging
from typing import Annotated, Any, Optional

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.agents.enrichment_agent import run_enrichment_agent
from app.agents.qa_agent import run_qa_agent
from app.agents.validation_agent import run_validation_agent

logger = logging.getLogger(__name__)


class ProviderState(TypedDict):
    provider: dict
    validation_result: Optional[dict]
    enrichment_result: Optional[dict]
    qa_result: Optional[dict]
    status: str
    error: Optional[str]


async def validate_node(state: ProviderState) -> dict:
    try:
        result = await run_validation_agent(state["provider"])
        if result["status"] == "failed":
            return {
                "validation_result": result,
                "status": "failed",
                "error": result.get("error"),
            }
        return {
            "validation_result": result,
            "status": "validated",
            "error": None,
        }
    except Exception as exc:
        logger.error("validate_node error: %s", exc)
        return {
            "validation_result": None,
            "status": "failed",
            "error": "Validation agent encountered an unexpected error",
        }


async def enrich_node(state: ProviderState) -> dict:
    try:
        result = await run_enrichment_agent(state["provider"])
        return {
            "enrichment_result": result,
            "status": "enriched",
        }
    except Exception as exc:
        logger.error("enrich_node error: %s", exc)
        return {
            "enrichment_result": None,
            "status": "validated",
            "error": "Enrichment agent encountered an unexpected error",
        }


async def qa_node(state: ProviderState) -> dict:
    try:
        enrichment = state.get("enrichment_result")
        if enrichment and enrichment.get("enriched_provider"):
            provider_to_check = enrichment["enriched_provider"]
        else:
            provider_to_check = state["provider"]
        result = await run_qa_agent(provider_to_check)
        final_status = "approved" if result["decision"] == "approved" else "flagged"
        return {
            "qa_result": result,
            "status": final_status,
        }
    except Exception as exc:
        logger.error("qa_node error: %s", exc)
        return {
            "qa_result": None,
            "status": "flagged",
            "error": "QA agent encountered an unexpected error",
        }


async def finalize_node(state: ProviderState) -> dict:
    return {"status": state.get("status", "failed")}


def should_enrich(state: ProviderState) -> str:
    if state.get("status") == "failed":
        return "finalize"
    return "enrich"


def build_workflow() -> Any:
    graph = StateGraph(ProviderState)
    graph.add_node("validate", validate_node)
    graph.add_node("enrich", enrich_node)
    graph.add_node("qa", qa_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "validate")
    graph.add_conditional_edges(
        "validate",
        should_enrich,
        {"enrich": "enrich", "finalize": "finalize"},
    )
    graph.add_edge("enrich", "qa")
    graph.add_edge("qa", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


workflow = build_workflow()


async def run_validation_workflow(provider: dict) -> ProviderState:
    initial_state: ProviderState = {
        "provider": provider,
        "validation_result": None,
        "enrichment_result": None,
        "qa_result": None,
        "status": "pending",
        "error": None,
    }
    final_state = await workflow.ainvoke(initial_state)
    return final_state
