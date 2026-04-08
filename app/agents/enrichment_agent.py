"""
MIT License
Enrichment agent: standardizes and fills missing provider fields using Groq or rule-based logic.
"""
import json
import logging
import re
from typing import Optional

from app.services.groq_client import GroqClient, GroqClientError, get_groq_client

logger = logging.getLogger(__name__)

CONTROLLED_SPECIALTIES = [
    "Internal Medicine",
    "Family Medicine",
    "Cardiology",
    "Orthopedics",
    "Neurology",
    "Pediatrics",
    "Dermatology",
    "Psychiatry",
    "Oncology",
    "Emergency Medicine",
]

STATE_AREA_CODES = {
    "CA": {"213", "310", "323", "408", "415", "424", "442", "510", "530", "559",
           "562", "619", "626", "628", "650", "657", "661", "707", "714", "747",
           "760", "805", "818", "831", "858", "909", "916", "925", "949", "951"},
    "TX": {"210", "214", "254", "281", "325", "361", "409", "430", "432", "469",
           "512", "682", "713", "726", "737", "806", "817", "830", "832", "903",
           "915", "936", "940", "956", "972", "979"},
    "NY": {"212", "315", "332", "347", "516", "518", "585", "607", "631", "646",
           "680", "716", "718", "838", "845", "914", "917", "929", "934"},
    "FL": {"239", "305", "321", "352", "386", "407", "561", "689", "727", "754",
           "772", "786", "813", "850", "863", "904", "941", "954"},
    "IL": {"217", "224", "309", "312", "331", "447", "464", "618", "630", "708",
           "730", "779", "815", "847", "872"},
}


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return phone


def _normalize_specialty(specialty: str) -> str:
    if specialty in CONTROLLED_SPECIALTIES:
        return specialty
    specialty_lower = specialty.lower()
    for controlled in CONTROLLED_SPECIALTIES:
        if controlled.lower() in specialty_lower or specialty_lower in controlled.lower():
            return controlled
    return specialty


def _normalize_address(address: str) -> str:
    address = address.strip()
    abbrevs = {
        r"\bStreet\b": "St",
        r"\bAvenue\b": "Ave",
        r"\bBoulevard\b": "Blvd",
        r"\bDrive\b": "Dr",
        r"\bLane\b": "Ln",
        r"\bRoad\b": "Rd",
        r"\bCourt\b": "Ct",
        r"\bPlace\b": "Pl",
        r"\bSuite\b": "Ste",
    }
    for pattern, replacement in abbrevs.items():
        address = re.sub(pattern, replacement, address, flags=re.IGNORECASE)
    return address


def _rule_based_enrich(provider: dict) -> tuple[dict, list]:
    enriched = dict(provider)
    modified = []

    if enriched.get("phone"):
        normalized = _normalize_phone(enriched["phone"])
        if normalized != enriched["phone"]:
            enriched["phone"] = normalized
            modified.append("phone")

    if enriched.get("specialty"):
        normalized = _normalize_specialty(enriched["specialty"])
        if normalized != enriched["specialty"]:
            enriched["specialty"] = normalized
            modified.append("specialty")

    if enriched.get("address"):
        normalized = _normalize_address(enriched["address"])
        if normalized != enriched["address"]:
            enriched["address"] = normalized
            modified.append("address")

    if enriched.get("state"):
        enriched["state"] = enriched["state"].upper().strip()

    return enriched, modified


async def _groq_enrich(
    provider: dict,
    groq_client: GroqClient,
) -> tuple[dict, list]:
    system_prompt = (
        "You are a healthcare data standardization assistant. "
        "Given a provider record, return a JSON object with the same fields but standardized. "
        "Rules: phone in E.164 format (+1XXXXXXXXXX for US), specialty must be one of: "
        + ", ".join(CONTROLLED_SPECIALTIES)
        + ". Address should use standard abbreviations. "
        "State should be 2-letter uppercase abbreviation. "
        "Return ONLY valid JSON, no explanation."
    )
    user_prompt = f"Standardize this provider record:\n{json.dumps(provider, default=str)}"

    try:
        response_text = await groq_client.complete(system_prompt, user_prompt)
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON found in Groq response")
        enriched_data = json.loads(json_match.group())
        modified = []
        allowed_fields = {"phone", "specialty", "address", "city", "state", "zip_code", "name"}
        for field in allowed_fields:
            if field in enriched_data and enriched_data[field] != provider.get(field):
                modified.append(field)
        enriched = dict(provider)
        for field in allowed_fields:
            if field in enriched_data:
                enriched[field] = str(enriched_data[field])
        return enriched, modified
    except (GroqClientError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Groq enrichment failed, falling back to rule-based: %s", exc)
        return _rule_based_enrich(provider)


async def run_enrichment_agent(
    provider: dict,
    groq_client: Optional[GroqClient] = None,
) -> dict:
    if groq_client is None:
        groq_client = get_groq_client()

    if groq_client is not None:
        enriched, modified = await _groq_enrich(provider, groq_client)
    else:
        enriched, modified = _rule_based_enrich(provider)

    field_confidences = {field: 0.95 for field in modified}

    return {
        "status": "enriched",
        "enriched_provider": enriched,
        "modified_fields": modified,
        "field_confidences": field_confidences,
        "enrichment_method": "groq" if groq_client else "rule_based",
    }
