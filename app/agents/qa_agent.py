"""
MIT License
QA agent: cross-checks provider records for internal consistency and assigns quality scores.
"""
import logging
import re

logger = logging.getLogger(__name__)

AUTO_APPROVE_THRESHOLD = 0.85

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

STATE_ZIP_PREFIXES = {
    "CA": {"900", "901", "902", "903", "904", "905", "906", "907", "908", "909",
           "910", "911", "912", "913", "914", "915", "916", "917", "918", "919",
           "920", "921", "922", "923", "924", "925", "926", "927", "928", "930",
           "931", "932", "933", "934", "935", "936", "937", "938", "939", "940",
           "941", "942", "943", "944", "945", "946", "947", "948", "949", "950",
           "951", "952", "953", "954", "955", "956", "957", "958", "959", "960",
           "961"},
    "TX": {"750", "751", "752", "753", "754", "755", "756", "757", "758", "759",
           "760", "761", "762", "763", "764", "765", "766", "767", "768", "769",
           "770", "771", "772", "773", "774", "775", "776", "777", "778", "779",
           "780", "781", "782", "783", "784", "785", "786", "787", "788", "789",
           "790", "791", "792", "793", "794", "795", "796", "797", "798", "799"},
    "NY": {"100", "101", "102", "103", "104", "105", "106", "107", "108", "109",
           "110", "111", "112", "113", "114", "115", "116", "117", "118", "119",
           "120", "121", "122", "123", "124", "125", "126", "127", "128", "129",
           "130", "131", "132", "133", "134", "135", "136", "137", "138", "139",
           "140", "141", "142", "143", "144", "145", "146", "147", "148", "149"},
    "FL": {"320", "321", "322", "323", "324", "325", "326", "327", "328", "329",
           "330", "331", "332", "333", "334", "335", "336", "337", "338", "339",
           "340", "341", "342", "344", "346", "347", "349"},
    "IL": {"600", "601", "602", "603", "604", "605", "606", "607", "608", "609",
           "610", "611", "612", "613", "614", "615", "616", "617", "618", "619",
           "620", "622", "623", "624", "625", "626", "627", "628", "629"},
}


def _check_zip_state(state: str, zip_code: str) -> tuple[bool, str]:
    state = state.upper().strip()
    zip_clean = re.sub(r"\D", "", zip_code)[:3]
    if not zip_clean or state not in STATE_ZIP_PREFIXES:
        return True, ""
    if zip_clean in STATE_ZIP_PREFIXES[state]:
        return True, ""
    return False, f"Zip prefix {zip_clean} does not match state {state}"


def _check_phone_state(state: str, phone: str) -> tuple[bool, str]:
    state = state.upper().strip()
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return True, ""
    area_code = digits[:3]
    if state not in STATE_AREA_CODES:
        return True, ""
    if area_code in STATE_AREA_CODES[state]:
        return True, ""
    return False, f"Area code {area_code} does not match state {state}"


def _check_npi_format(npi: str) -> tuple[bool, str]:
    if re.fullmatch(r"\d{10}", npi):
        return True, ""
    return False, f"NPI {npi} is not a valid 10-digit number"


def _check_required_fields(provider: dict) -> list:
    missing = []
    required = ["npi", "name", "specialty", "phone", "address", "city", "state", "zip_code"]
    for field in required:
        value = provider.get(field, "")
        if not value or not str(value).strip():
            missing.append(field)
    return missing


async def run_qa_agent(provider: dict) -> dict:
    flags = []
    issues = []

    npi_ok, npi_msg = _check_npi_format(provider.get("npi", ""))
    if not npi_ok:
        flags.append("npi_format")
        issues.append(npi_msg)

    missing = _check_required_fields(provider)
    if missing:
        flags.append("missing_fields")
        issues.append(f"Missing required fields: {', '.join(missing)}")

    state = provider.get("state", "")
    zip_code = provider.get("zip_code", "")
    if state and zip_code:
        zip_ok, zip_msg = _check_zip_state(state, zip_code)
        if not zip_ok:
            flags.append("zip_state_mismatch")
            issues.append(zip_msg)

    phone = provider.get("phone", "")
    if state and phone:
        phone_ok, phone_msg = _check_phone_state(state, phone)
        if not phone_ok:
            flags.append("phone_state_mismatch")
            issues.append(phone_msg)

    total_checks = 4
    passed_checks = total_checks - len(set(["npi_format", "missing_fields", "zip_state_mismatch", "phone_state_mismatch"]) & set(flags))
    quality_score = round(passed_checks / total_checks, 2)

    if missing:
        penalty = min(0.3, len(missing) * 0.05)
        quality_score = max(0.0, quality_score - penalty)

    decision = "approved" if quality_score >= AUTO_APPROVE_THRESHOLD else "flagged"

    return {
        "quality_score": quality_score,
        "decision": decision,
        "flags": flags,
        "issues": issues,
        "reasoning": (
            f"Quality score {quality_score:.2f}. "
            + (f"Issues found: {'; '.join(issues)}" if issues else "No issues found.")
        ),
        "auto_approved": decision == "approved",
    }
