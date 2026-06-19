"""Integration tests for main.py FastAPI routes using TestClient."""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-for-integration-tests")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app, MOCK_WEEKS, signer

client = TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Helper to mint a signed session cookie
# ---------------------------------------------------------------------------
def session_cookie(username: str) -> dict:
    token = signer.dumps({"username": username})
    return {"hf_session": token}


# ---------------------------------------------------------------------------
# GET / — root route
# ---------------------------------------------------------------------------

class TestRoot:
    def test_returns_200(self, tmp_path, monkeypatch):
        html_file = tmp_path / "index.html"
        html_file.write_text("<html><body>test</body></html>")
        monkeypatch.chdir(tmp_path)
        (tmp_path / "static").mkdir()
        (tmp_path / "static" / "index.html").write_text("<html><body>app</body></html>")
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_returns_html_content(self, tmp_path, monkeypatch):
        (tmp_path / "static").mkdir()
        (tmp_path / "static" / "index.html").write_text("<html><body>ntu-mara</body></html>")
        monkeypatch.chdir(tmp_path)
        r = client.get("/")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/guest-data
# ---------------------------------------------------------------------------

class TestGuestData:
    def test_returns_200_without_auth(self):
        r = client.get("/api/guest-data")
        assert r.status_code == 200

    def test_response_shape(self):
        r = client.get("/api/guest-data")
        data = r.json()
        assert data["username"] == "Guest"
        assert data["guest"] is True
        assert data["user_col_found"] is False
        assert isinstance(data["weeks"], list)

    def test_weeks_count_matches_mock(self):
        r = client.get("/api/guest-data")
        assert len(r.json()["weeks"]) == len(MOCK_WEEKS)

    def test_week_items_have_required_keys(self):
        r = client.get("/api/guest-data")
        required = {"week", "theme", "objectives", "max_points", "admin_step", "user_score"}
        for w in r.json()["weeks"]:
            assert required <= w.keys()

    def test_user_scores_are_none(self):
        r = client.get("/api/guest-data")
        for w in r.json()["weeks"]:
            assert w["user_score"] is None


# ---------------------------------------------------------------------------
# GET /api/syllabus-data
# ---------------------------------------------------------------------------

class TestSyllabusData:
    @patch("main.OAUTH_CLIENT_ID", "")  # OAuth not configured → no auth required
    @patch("main._worksheet")
    def test_falls_back_to_mock_on_sheet_error(self, mock_ws):
        mock_ws.side_effect = Exception("Sheets unreachable")
        r = client.get("/api/syllabus-data")
        assert r.status_code == 200
        data = r.json()
        assert data["fallback"] is True
        assert len(data["weeks"]) == len(MOCK_WEEKS)

    @patch("main.OAUTH_CLIENT_ID", "fake-client-id")
    def test_requires_auth_when_oauth_configured(self):
        r = client.get("/api/syllabus-data")
        assert r.status_code == 401

    @patch("main.OAUTH_CLIENT_ID", "")
    @patch("main._worksheet")
    def test_returns_data_from_sheet(self, mock_ws):
        mock_ws.return_value.get_all_values.return_value = [
            ["Week", "Theme", "Learning objectives", "Max Points", "Admin Step", "testuser"],
            ["Week 1", "SQL Basics", "SELECT queries", "3", "1", "2"],
        ]
        r = client.get("/api/syllabus-data")
        assert r.status_code == 200
        data = r.json()
        assert data["weeks"][0]["week"] == "Week 1"
        assert data["weeks"][0]["max_points"] == 3

    @patch("main.OAUTH_CLIENT_ID", "")
    @patch("main._worksheet")
    def test_user_col_found_when_username_in_headers(self, mock_ws):
        mock_ws.return_value.get_all_values.return_value = [
            ["Week", "Theme", "Learning objectives", "Max Points", "Admin Step", "alice"],
            ["Week 1", "SQL", "obj", "3", "1", "2"],
        ]
        r = client.get(
            "/api/syllabus-data",
            headers={"X-HF-Username": "alice"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["user_col_found"] is True
        assert data["weeks"][0]["user_score"] == 2

    @patch("main.OAUTH_CLIENT_ID", "")
    @patch("main._worksheet")
    def test_user_col_not_found_when_username_absent(self, mock_ws):
        mock_ws.return_value.get_all_values.return_value = [
            ["Week", "Theme", "Learning objectives", "Max Points", "Admin Step"],
            ["Week 1", "SQL", "obj", "3", "1"],
        ]
        r = client.get(
            "/api/syllabus-data",
            headers={"X-HF-Username": "alice"},
        )
        data = r.json()
        assert data["user_col_found"] is False

    @patch("main.OAUTH_CLIENT_ID", "")
    @patch("main._worksheet")
    def test_skips_empty_rows(self, mock_ws):
        mock_ws.return_value.get_all_values.return_value = [
            ["Week", "Theme", "Learning objectives", "Max Points", "Admin Step"],
            ["Week 1", "SQL", "obj", "3", "1"],
            ["", "", "", "", ""],
            ["Week 2", "Joins", "obj2", "2", "1"],
        ]
        r = client.get("/api/syllabus-data")
        assert len(r.json()["weeks"]) == 2

    @patch("main.OAUTH_CLIENT_ID", "")
    @patch("main._worksheet")
    def test_zero_user_score_preserved(self, mock_ws):
        """A score of 0 must not be confused with null (falsy zero bug guard)."""
        mock_ws.return_value.get_all_values.return_value = [
            ["Week", "Theme", "Learning objectives", "Max Points", "Admin Step", "alice"],
            ["Week 1", "SQL", "obj", "3", "1", "0"],
        ]
        r = client.get(
            "/api/syllabus-data",
            headers={"X-HF-Username": "alice"},
        )
        week = r.json()["weeks"][0]
        assert week["user_score"] == 0  # not None


# ---------------------------------------------------------------------------
# GET /login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_redirects_when_oauth_configured(self):
        with patch("main.OAUTH_CLIENT_ID", "my-client-id"):
            r = client.get("/login", follow_redirects=False)
        assert r.status_code in (302, 307)
        assert "huggingface.co" in r.headers["location"]

    def test_sets_oauth_state_cookie(self):
        with patch("main.OAUTH_CLIENT_ID", "my-client-id"):
            r = client.get("/login", follow_redirects=False)
        assert "oauth_state" in r.cookies

    def test_oauth_state_cookie_works_in_iframe(self):
        """HF Spaces serves the app in an iframe — the state cookie must be
        SameSite=None; Secure or browsers drop it and every callback 400s."""
        with patch("main.OAUTH_CLIENT_ID", "my-client-id"):
            r = client.get("/login", follow_redirects=False)
        set_cookie = r.headers.get("set-cookie", "").lower()
        assert "samesite=none" in set_cookie
        assert "secure" in set_cookie

    def test_returns_501_when_no_client_id(self):
        with patch("main.OAUTH_CLIENT_ID", ""):
            r = client.get("/login")
        assert r.status_code == 501


# ---------------------------------------------------------------------------
# GET /logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_redirects_to_root(self):
        r = client.get("/logout", follow_redirects=False)
        assert r.status_code in (302, 307)
        assert r.headers["location"] == "/"

    def test_clears_session_cookie(self):
        r = client.get("/logout", follow_redirects=False, cookies=session_cookie("alice"))
        # Cookie should be deleted (set-cookie header with empty/expired value)
        set_cookie = r.headers.get("set-cookie", "")
        assert "hf_session" in set_cookie


# ---------------------------------------------------------------------------
# GET /callback — CSRF guard
# ---------------------------------------------------------------------------

class TestCallbackCSRF:
    def test_missing_code_returns_400(self):
        r = client.get("/callback")
        assert r.status_code == 400

    def test_error_param_redirects(self):
        r = client.get("/callback?error=access_denied", follow_redirects=False)
        assert r.status_code in (302, 307)
        assert "error=oauth_failed" in r.headers["location"]

    def test_state_mismatch_returns_400(self):
        cookies = {"oauth_state": "correct-state"}
        r = client.get(
            "/callback?code=somecode&state=wrong-state",
            cookies=cookies,
        )
        assert r.status_code == 400

    def test_missing_state_with_no_cookie_should_reject(self):
        """CSRF guard: no state param + no stored cookie must return 400, not proceed."""
        r = client.get("/callback?code=somecode")
        assert r.status_code == 400
