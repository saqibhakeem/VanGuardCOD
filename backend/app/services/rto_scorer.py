"""Deterministic heuristic RTO risk scoring (TRD section 2.2)."""

from __future__ import annotations

import math
import re

from pydantic import BaseModel, ConfigDict, Field

_DIGIT_PATTERN = re.compile(r"\d")
_KNOWN_CITIES = (
    "karachi",
    "lahore",
    "islamabad",
    "rawalpindi",
    "faisalabad",
    "multan",
    "peshawar",
    "quetta",
    "hyderabad",
    "sialkot",
    "gujranwala",
)

BASE_RISK = 20.0
NO_HOUSE_NUMBER_WEIGHT = 30.0
SHORT_ADDRESS_WEIGHT = 25.0
COD_AMOUNT_WEIGHT = 25.0
MIN_ADDRESS_WORDS = 5
HIGH_RISK_THRESHOLD = 60


class RtoAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=100)
    has_house_number: bool
    address_word_count: int = Field(ge=0)
    cod_factor: float = Field(ge=0.0, le=1.0)
    factors: dict[str, float]
    missing_components: list[str]
    is_high_risk: bool


def _has_house_number(raw_address: str) -> bool:
    return _DIGIT_PATTERN.search(raw_address) is not None


def _word_count(raw_address: str) -> int:
    return len(raw_address.split())


def _cod_factor(cod_amount: float, max_auto_approve_cod: float) -> float:
    if max_auto_approve_cod <= 0:
        return 1.0 if cod_amount > 0 else 0.0
    return min(1.0, max(0.0, cod_amount) / max_auto_approve_cod)


def identify_missing_address_components(
    raw_address: str, verified_landmark: str | None = None
) -> list[str]:
    """Return the address fields an outbound verifier should collect."""

    missing: list[str] = []
    if not _has_house_number(raw_address):
        missing.append("house_or_plot_number")
    if _word_count(raw_address) < MIN_ADDRESS_WORDS:
        missing.append("street_or_area_detail")
    normalized = raw_address.lower()
    if not any(city in normalized for city in _KNOWN_CITIES):
        missing.append("city")
    if not (verified_landmark and verified_landmark.strip()):
        missing.append("verified_landmark")
    return missing


def calculate_rto_risk_score(
    raw_address: str,
    cod_amount: float,
    max_auto_approve_cod: float,
) -> int:
    """Compute the integer risk score in the inclusive range 0 to 100."""

    no_house_number = 0.0 if _has_house_number(raw_address) else 1.0
    short_address = 0.0 if _word_count(raw_address) >= MIN_ADDRESS_WORDS else 1.0
    raw_score = (
        BASE_RISK
        + NO_HOUSE_NUMBER_WEIGHT * no_house_number
        + SHORT_ADDRESS_WEIGHT * short_address
        + COD_AMOUNT_WEIGHT * _cod_factor(cod_amount, max_auto_approve_cod)
    )
    clamped = min(100.0, max(0.0, raw_score))
    return int(math.floor(clamped + 0.5))


def assess_rto_risk(
    raw_address: str,
    cod_amount: float,
    max_auto_approve_cod: float,
    verified_landmark: str | None = None,
) -> RtoAssessment:
    no_house_number = 0.0 if _has_house_number(raw_address) else 1.0
    short_address = 0.0 if _word_count(raw_address) >= MIN_ADDRESS_WORDS else 1.0
    cod_factor = _cod_factor(cod_amount, max_auto_approve_cod)
    score = calculate_rto_risk_score(raw_address, cod_amount, max_auto_approve_cod)

    return RtoAssessment(
        score=score,
        has_house_number=bool(no_house_number == 0.0),
        address_word_count=_word_count(raw_address),
        cod_factor=round(cod_factor, 4),
        factors={
            "base": BASE_RISK,
            "no_house_number": NO_HOUSE_NUMBER_WEIGHT * no_house_number,
            "short_address": SHORT_ADDRESS_WEIGHT * short_address,
            "cod_amount": round(COD_AMOUNT_WEIGHT * cod_factor, 4),
        },
        missing_components=identify_missing_address_components(raw_address, verified_landmark),
        is_high_risk=score >= HIGH_RISK_THRESHOLD,
    )
