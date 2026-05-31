"""
Hero-SMS API helpers for GoPay protocol flows.

Extracted from test_full_e2e.py — pure utility functions, no flow logic.
"""
from __future__ import annotations

import logging
import os
import re
import time

import tls_client

log = logging.getLogger(__name__)

HEROSMS_API = "https://hero-sms.com"
SMS_TIMEOUT = 120


def sms_api(api_key: str, action: str, params: dict | None = None, retries: int = 3) -> str:
    p = {"api_key": api_key, "action": action}
    if params:
        p.update(params)
    for i in range(1, retries + 1):
        try:
            s = tls_client.Session(client_identifier="chrome_120")
            r = s.get(f"{HEROSMS_API}/stubs/handler_api.php", params=p, timeout_seconds=30)
            return r.text.strip()
        except Exception as e:
            log.debug("sms_api attempt %d: %s", i, e)
            if i < retries:
                time.sleep(3)
    raise RuntimeError(f"sms_api {action} failed after {retries} retries")


def sms_get_number(api_key: str) -> tuple[str | None, str | None]:
    resp = sms_api(api_key, "getNumber", {"service": "ni", "country": "6"})
    log.info("getNumber: %s", resp)
    if resp.startswith("ACCESS_NUMBER:"):
        parts = resp.split(":")
        return f"+{parts[2]}", parts[1]
    log.warning("getNumber failed: %s", resp)
    return None, None


def sms_wait_code(api_key: str, aid: str, timeout: int = SMS_TIMEOUT) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = sms_api(api_key, "getStatus", {"id": aid})
        except Exception:
            time.sleep(5)
            continue
        if resp.startswith("STATUS_OK:"):
            code = resp.split(":", 1)[1]
            m = re.search(r"\b(\d{4,6})\b", code)
            return m.group(1) if m else code
        if resp == "STATUS_CANCEL":
            log.warning("SMS activation cancelled")
            return None
        time.sleep(5)
    return None


def sms_request_another(api_key: str, aid: str) -> bool:
    try:
        resp = sms_api(api_key, "setStatus", {"id": aid, "status": "3"})
        log.info("sms_request_another: %s", resp)
        return "ACCESS_RETRY_GET" in resp
    except Exception:
        return False


def sms_cancel(api_key: str, aid: str) -> None:
    try:
        sms_api(api_key, "setStatus", {"id": aid, "status": "8"})
    except Exception:
        pass


def sms_done(api_key: str, aid: str) -> None:
    try:
        sms_api(api_key, "setStatus", {"id": aid, "status": "6"})
    except Exception:
        pass


# ========== API Error Helpers ==========

def is_waf_block(result: dict) -> bool:
    body = result.get("body", {})
    if isinstance(body, dict) and "raw" in body:
        return "WAF Block Page" in body["raw"]
    return False


def is_rate_limited(result: dict) -> bool:
    errors = result.get("body", {}).get("errors", [])
    if errors:
        code = errors[0].get("code", "")
        return "ratelimit" in code.lower() or "rate_limit" in code.lower()
    return result.get("status") == 429


def get_error_code(result: dict) -> str:
    errors = result.get("body", {}).get("errors", [])
    return errors[0].get("code", "") if errors else ""


def api_call_with_retry(fn, *args, max_retries: int = 2, **kwargs) -> dict:
    """Retry API call on WAF block or transient errors."""
    result = {}
    for attempt in range(max_retries + 1):
        result = fn(*args, **kwargs)
        if result["status"] in (200, 201, 204):
            return result
        if is_waf_block(result):
            if attempt < max_retries:
                wait = 5 * (attempt + 1)
                log.warning("WAF blocked, retrying in %ds... (%d/%d)", wait, attempt + 1, max_retries)
                time.sleep(wait)
                continue
        if is_rate_limited(result):
            if attempt < max_retries:
                wait = 30 * (attempt + 1)
                log.warning("Rate limited, retrying in %ds...", wait)
                time.sleep(wait)
                continue
        return result
    return result
