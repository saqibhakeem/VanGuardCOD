"""Hashing and normalization helpers shared by API and seed code."""

from __future__ import annotations

import hashlib
import re

_PHONE_SEPARATORS = re.compile(r"[\s\-().]+")


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.strip().encode("utf-8")).hexdigest()


def normalize_phone(raw_phone: str) -> str:
    phone = _PHONE_SEPARATORS.sub("", raw_phone.strip())
    if phone.startswith("00"):
        phone = f"+{phone[2:]}"
    if phone.startswith("+"):
        digits = phone[1:]
        return f"+{digits}" if digits.isdigit() else phone
    digits = phone.lstrip("0")
    if not digits.isdigit():
        return phone
    if len(digits) == 10:
        return f"+92{digits}"
    return f"+{digits}"
