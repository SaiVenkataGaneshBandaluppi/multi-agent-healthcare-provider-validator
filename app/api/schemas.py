"""
MIT License
Pydantic v2 request and response schemas with strict input validation.
"""
import re
import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _strip_whitespace(v: str) -> str:
    return v.strip() if isinstance(v, str) else v


class ProviderInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    npi: str = Field(..., description="10-digit NPI number")
    name: str = Field(..., min_length=2, max_length=200)
    specialty: str = Field(..., min_length=1, max_length=200)
    phone: str = Field(..., min_length=1, max_length=20)
    address: str = Field(..., min_length=1, max_length=500)
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=2, max_length=2)
    zip_code: str = Field(..., description="5 or 9-digit zip code")

    @field_validator("npi")
    @classmethod
    def validate_npi(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"\d{10}", v):
            raise ValueError("NPI must be exactly 10 numeric digits")
        return v

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"\d{5}(-\d{4})?|\d{9}", v):
            raise ValueError("Zip code must be 5 or 9 digits")
        return v

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("name", "specialty", "phone", "address", "city")
    @classmethod
    def no_script_tags(cls, v: str) -> str:
        if re.search(r"<script|javascript:|on\w+\s*=", v, re.IGNORECASE):
            raise ValueError("Input contains disallowed content")
        return v


class ProviderResponse(BaseModel):
    id: uuid.UUID
    npi: str
    name: str
    specialty: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    zip_code: Optional[str]
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ValidationRequest(BaseModel):
    providers: list[ProviderInput] = Field(..., max_length=50)


class ProviderResultItem(BaseModel):
    npi: Optional[str]
    name: Optional[str]
    final_status: str
    confidence_score: float
    validation_result: Optional[dict]
    enrichment_result: Optional[dict]
    qa_result: Optional[dict]
    error: Optional[str]


class ValidationResponse(BaseModel):
    batch_id: str
    total: int
    approved: int
    flagged: int
    failed: int
    processing_time_seconds: float
    results: list[ProviderResultItem]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class ErrorResponse(BaseModel):
    detail: str
    code: str


class PaginatedProviders(BaseModel):
    total: int
    page: int
    size: int
    items: list[ProviderResponse]


class StatsResponse(BaseModel):
    total_providers: int
    approval_rate: float
    average_confidence_score: float
    providers_by_status: dict[str, int]
    providers_by_specialty: dict[str, int]
