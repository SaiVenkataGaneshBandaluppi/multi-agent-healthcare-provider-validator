"""
MIT License
Validation agent: verifies NPI numbers against the NPPES CMS registry.
"""
import logging
import re
from typing import Optional

from app.services.nppes_client import (
    NPPESAPIError,
    NPPESClient,
    NPPESNotFoundError,
    NPPESRateLimitError,
    get_nppes_client,
)

logger = logging.getLogger(__name__)

SPECIALTY_TAXONOMY_MAP = {
    "Internal Medicine": ["207R00000X"],
    "Family Medicine": ["207Q00000X"],
    "Cardiology": ["207RC0000X"],
    "Orthopedics": ["207X00000X"],
    "Neurology": ["2084N0400X"],
    "Pediatrics": ["208000000X"],
    "Dermatology": ["207N00000X"],
    "Psychiatry": ["2084P0800X"],
    "Oncology": ["207RX0202X"],
    "Emergency Medicine": ["207P00000X"],
}


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _extract_nppes_name(record: dict) -> str:
    basic = record.get("basic", {})
    first = basic.get("first_name", "")
    last = basic.get("last_name", "")
    org = basic.get("organization_name", "")
    if org:
        return _normalize_name(org)
    return _normalize_name(f"{first} {last}")


def _extract_nppes_address(record: dict) -> dict:
    addresses = record.get("addresses", [])
    for addr in addresses:
        if addr.get("address_purpose") == "LOCATION":
            return addr
    return addresses[0] if addresses else {}


def _extract_nppes_taxonomies(record: dict) -> list:
    return [t.get("code", "") for t in record.get("taxonomies", [])]


def _compute_confidence(matched: list, total: int) -> float:
    if total == 0:
        return 0.0
    return round(len(matched) / total, 2)


async def run_validation_agent(
    provider: dict,
    nppes_client: Optional[NPPESClient] = None,
) -> dict:
    npi = provider.get("npi", "")

    if not re.fullmatch(r"\d{10}", npi):
        return {
            "status": "failed",
            "confidence_score": 0.0,
            "matched_fields": [],
            "mismatched_fields": ["npi_format"],
            "error": "NPI must be exactly 10 numeric digits",
            "nppes_record": None,
        }

    if nppes_client is None:
        nppes_client = await get_nppes_client()

    try:
        nppes_record = await nppes_client.lookup_npi(npi)
    except NPPESNotFoundError:
        return {
            "status": "failed",
            "confidence_score": 0.0,
            "matched_fields": [],
            "mismatched_fields": ["npi_not_found"],
            "error": f"NPI {npi} not found in NPPES registry",
            "nppes_record": None,
        }
    except NPPESRateLimitError:
        return {
            "status": "failed",
            "confidence_score": 0.0,
            "matched_fields": [],
            "mismatched_fields": [],
            "error": "NPPES API rate limit exceeded, please retry later",
            "nppes_record": None,
        }
    except NPPESAPIError as exc:
        return {
            "status": "failed",
            "confidence_score": 0.0,
            "matched_fields": [],
            "mismatched_fields": [],
            "error": f"NPPES API error: {exc}",
            "nppes_record": None,
        }

    matched = []
    mismatched = []
    checks = 0

    # Name check
    provider_name = _normalize_name(provider.get("name", ""))
    nppes_name = _extract_nppes_name(nppes_record)
    if provider_name and nppes_name:
        checks += 1
        if provider_name in nppes_name or nppes_name in provider_name:
            matched.append("name")
        else:
            mismatched.append("name")

    # Address check
    nppes_addr = _extract_nppes_address(nppes_record)
    provider_state = provider.get("state", "").upper()
    nppes_state = nppes_addr.get("state", "").upper()
    if provider_state and nppes_state:
        checks += 1
        if provider_state == nppes_state:
            matched.append("state")
        else:
            mismatched.append("state")

    provider_zip = re.sub(r"\D", "", provider.get("zip_code", ""))[:5]
    nppes_zip = re.sub(r"\D", "", nppes_addr.get("postal_code", ""))[:5]
    if provider_zip and nppes_zip:
        checks += 1
        if provider_zip == nppes_zip:
            matched.append("zip_code")
        else:
            mismatched.append("zip_code")

    # Taxonomy / specialty check
    provider_specialty = provider.get("specialty", "")
    nppes_codes = _extract_nppes_taxonomies(nppes_record)
    expected_codes = SPECIALTY_TAXONOMY_MAP.get(provider_specialty, [])
    if expected_codes and nppes_codes:
        checks += 1
        if any(code in nppes_codes for code in expected_codes):
            matched.append("specialty")
        else:
            mismatched.append("specialty")

    confidence = _compute_confidence(matched, max(checks, 1))

    return {
        "status": "validated",
        "confidence_score": confidence,
        "matched_fields": matched,
        "mismatched_fields": mismatched,
        "error": None,
        "nppes_record": {
            "name": nppes_name,
            "state": nppes_state,
            "zip_code": nppes_zip,
            "taxonomies": nppes_codes[:5],
        },
    }
