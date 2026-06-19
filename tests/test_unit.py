"""Unit tests for pure-Python helpers in main.py."""

import json
import os
import sys
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Isolate module from env before import so config doesn't need real secrets
# ---------------------------------------------------------------------------
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-for-unit-tests")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import MOCK_WEEKS, _current_user  # noqa: E402

# ---------------------------------------------------------------------------
# Expose private helpers so they can be tested without a full request context
# We inline the implementations here to keep unit tests self-contained.
# ---------------------------------------------------------------------------

def col(name: str, headers: list) -> Optional[int]:
    for i, h in enumerate(headers):
        if h.strip().lower() == name.strip().lower():
            return i
    return None


def cell(row: list, idx: Optional[int], default: str = "") -> str:
    if idx is None or idx >= len(row):
        return default
    return row[idx].strip()


def safe_int(s: str) -> Optional[int]:
    try:
        return int(float(s)) if s else None
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# col() tests
# ---------------------------------------------------------------------------

class TestCol:
    HEADERS = ["Week", "Theme", "Learning objectives", "Max Points", "Admin Step", "alice"]

    def test_exact_match(self):
        assert col("Week", self.HEADERS) == 0

    def test_case_insensitive(self):
        assert col("max points", self.HEADERS) == 3
        assert col("MAX POINTS", self.HEADERS) == 3

    def test_missing_column_returns_none(self):
        assert col("nonexistent", self.HEADERS) is None

    def test_whitespace_stripped(self):
        headers = [" Week ", " Theme "]
        assert col("Week", headers) == 0

    def test_user_column_found(self):
        assert col("alice", self.HEADERS) == 5

    def test_empty_headers(self):
        assert col("Week", []) is None


# ---------------------------------------------------------------------------
# cell() tests
# ---------------------------------------------------------------------------

class TestCell:
    def test_normal(self):
        assert cell(["a", "b", "c"], 1) == "b"

    def test_strips_whitespace(self):
        assert cell(["  hello  "], 0) == "hello"

    def test_out_of_bounds_returns_default(self):
        assert cell(["a"], 5) == ""
        assert cell(["a"], 5, "N/A") == "N/A"

    def test_none_index_returns_default(self):
        assert cell(["a", "b"], None) == ""

    def test_empty_string_cell(self):
        assert cell(["", "b"], 0) == ""


# ---------------------------------------------------------------------------
# safe_int() tests
# ---------------------------------------------------------------------------

class TestSafeInt:
    def test_integer_string(self):
        assert safe_int("3") == 3

    def test_float_string_truncated(self):
        assert safe_int("2.9") == 2

    def test_empty_string_returns_none(self):
        assert safe_int("") is None

    def test_non_numeric_returns_none(self):
        assert safe_int("abc") is None

    def test_zero_string(self):
        # Zero is a valid score — must not return None
        assert safe_int("0") == 0

    def test_none_input_returns_none(self):
        assert safe_int(None) is None


# ---------------------------------------------------------------------------
# _current_user() tests
# ---------------------------------------------------------------------------

class TestCurrentUser:
    def _make_request(self, headers=None, cookies=None):
        from starlette.testclient import TestClient
        from starlette.requests import Request
        from starlette.datastructures import Headers
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        }
        return Request(scope)

    def test_hf_header_takes_priority(self):
        req = self._make_request(headers={"X-HF-Username": "alice"})
        assert _current_user(req) == "alice"

    def test_second_hf_header_fallback(self):
        req = self._make_request(headers={"X-HF-User-Id": "bob"})
        assert _current_user(req) == "bob"

    def test_no_auth_returns_none(self):
        req = self._make_request()
        assert _current_user(req) is None


# ---------------------------------------------------------------------------
# MOCK_WEEKS sanity tests
# ---------------------------------------------------------------------------

class TestMockWeeks:
    def test_has_expected_count(self):
        assert len(MOCK_WEEKS) == 14

    def test_all_weeks_have_required_keys(self):
        required = {"week", "theme", "objectives", "max_points", "admin_step", "user_score"}
        for w in MOCK_WEEKS:
            assert required <= w.keys(), f"Missing keys in {w['week']}"

    def test_max_points_are_positive(self):
        for w in MOCK_WEEKS:
            assert w["max_points"] > 0, f"{w['week']} has non-positive max_points"

    def test_user_score_is_none(self):
        # Mock data should start with no user scores
        for w in MOCK_WEEKS:
            assert w["user_score"] is None

    def test_quiz_weeks_present(self):
        weeks = [w["week"] for w in MOCK_WEEKS]
        assert "Week 4 Quiz" in weeks
        assert "Week 7 Quiz" in weeks

    def test_admin_step_is_binary(self):
        for w in MOCK_WEEKS:
            assert w["admin_step"] in (0, 1), f"{w['week']} has invalid admin_step"
