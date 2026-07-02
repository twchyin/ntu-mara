import json
import os
import secrets
from typing import Optional

import gspread
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from google.oauth2.service_account import Credentials
from itsdangerous import BadSignature, URLSafeSerializer

app = FastAPI(title="NTU MARA Quest")

# ── Config ───────────────────────────────────────────────────────
OAUTH_CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID", "")
OAUTH_CLIENT_SECRET = os.environ.get("OAUTH_CLIENT_SECRET", "")
# APP_SECRET_KEY must be stable across restarts; HF Space secrets are the right place for it.
SECRET_KEY = os.environ.get("APP_SECRET_KEY") or secrets.token_hex(32)
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GOOGLE_SHEET_TAB = os.environ.get("GOOGLE_SHEET_TAB", "Sheet1")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
signer = URLSafeSerializer(SECRET_KEY)

HF_AUTH_URL = "https://huggingface.co/oauth/authorize"
HF_TOKEN_URL = "https://huggingface.co/oauth/token"
HF_USERINFO_URL = "https://huggingface.co/oauth/userinfo"

# ── Fallback dataset (used when Sheets is unreachable) ────────────
MOCK_WEEKS = [
    {"week": "Week 1",      "theme": "Intro & SQL Basics",            "objectives": "Install VS Code & SQLTools\nRead tables with SELECT / FROM / LIMIT\nFilter rows with WHERE and alias columns",                                               "max_points": 3,   "admin_step": 1, "user_score": None},
    {"week": "Week 2",      "theme": "Joins & Relationships",         "objectives": "Understand primary & foreign keys\nWrite INNER JOIN queries\nCompare LEFT vs INNER JOIN results",                                                             "max_points": 2,   "admin_step": 1, "user_score": None},
    {"week": "Week 3",      "theme": "Aggregation & Grouping",        "objectives": "Use GROUP BY and HAVING\nApply aggregate functions (SUM, AVG, COUNT)\nOrder and limit grouped results",                                                       "max_points": 2,   "admin_step": 1, "user_score": None},
    {"week": "Week 4",      "theme": "Subqueries & Window Functions", "objectives": "Write correlated subqueries\nUse ROW_NUMBER / RANK / LAG window functions\nApply CTEs for readable multi-step queries",                                       "max_points": 2,   "admin_step": 1, "user_score": None},
    {"week": "Week 4 Quiz", "theme": "SQL Fundamentals Assessment",   "objectives": "Complete the hands-on SQL assessment on your local environment\nQueries cover Weeks 1–4: SELECT, JOIN, GROUP BY, subqueries, window functions\nSubmit your .sql file via the course portal before the deadline", "max_points": 8,   "admin_step": 1, "user_score": None},
    {"week": "Week 5",      "theme": "Python & pandas Basics",        "objectives": "Load CSV data with pandas\nClean missing values\nExport cleaned datasets",                                                                                   "max_points": 2,   "admin_step": 1, "user_score": None},
    {"week": "Week 6",      "theme": "Merging & Exception Handling",  "objectives": "Merge two DataFrames\nHandle KeyError and missing columns\nWrite reusable helper functions",                                                                  "max_points": 2,   "admin_step": 1, "user_score": None},
    {"week": "Week 7",      "theme": "ETL Pipeline",                  "objectives": "Build an end-to-end ETL script\nSchedule a pipeline run\nGenerate a summary report",                                                                         "max_points": 2,   "admin_step": 0, "user_score": None},
    {"week": "Week 7 Quiz", "theme": "Python & ETL Skills Assessment","objectives": "Complete the hands-on Python & ETL assessment on your local environment\nImplement a full pipeline: ingest → transform → load → report\nSubmit your .py script and output files via the course portal before the deadline", "max_points": 9,   "admin_step": 0, "user_score": None},
    {"week": "Week 8",      "theme": "Query Optimisation",            "objectives": "Identify slow queries with EXPLAIN\nAdd indexes to speed up lookups\nCompare before/after execution plans",                                                   "max_points": 2,   "admin_step": 0, "user_score": None},
    {"week": "Week 9",      "theme": "Database Design",               "objectives": "Normalise a schema to 3NF\nDesign an ER diagram\nImplement constraints and foreign keys",                                                                    "max_points": 2,   "admin_step": 0, "user_score": None},
    {"week": "Week 10",     "theme": "Performance & Monitoring",      "objectives": "Set query timeouts\nMonitor slow-query logs\nOptimise multi-table joins",                                                                                     "max_points": 2,   "admin_step": 0, "user_score": None},
    {"week": "Week 11",     "theme": "Cloud Databases & APIs",        "objectives": "Connect to a cloud Postgres instance\nCall a REST API and store results in a table\nSecure credentials with environment variables",                           "max_points": 2,   "admin_step": 0, "user_score": None},
    {"week": "Week 12",     "theme": "Final Project & Showcase",      "objectives": "Present end-to-end data pipeline\nPeer code review session\nFinal portfolio submission",                                                                     "max_points": 3,   "admin_step": 0, "user_score": None},
]

# ── Helpers ──────────────────────────────────────────────────────

def _redirect_uri(request: Request) -> str:
    space_host = os.environ.get("SPACE_HOST", "")
    if space_host:
        return f"https://{space_host}/callback"
    host = request.headers.get("host", "localhost:7860")
    return f"http://{host}/callback"


def _current_user(request: Request) -> Optional[str]:
    # Some HF Space proxy configurations inject these headers automatically.
    for h in ("X-HF-Username", "X-HF-User-Id", "X-HF-User"):
        v = request.headers.get(h)
        if v:
            return v
    # Signed session cookie set after our own OAuth callback.
    cookie = request.cookies.get("hf_session")
    if cookie:
        try:
            data = signer.loads(cookie)
            return data.get("username")
        except BadSignature:
            pass
    return None


def _worksheet():
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON env var is not set")
    if not GOOGLE_SHEET_ID:
        raise ValueError("GOOGLE_SHEET_ID env var is not set")

    try:
        creds_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    except json.JSONDecodeError as exc:
        print("ERROR: Failed to parse GOOGLE_SERVICE_ACCOUNT_JSON secret.", flush=True)
        raise exc

    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(GOOGLE_SHEET_ID).worksheet(GOOGLE_SHEET_TAB)


# ── OAuth routes ─────────────────────────────────────────────────

@app.get("/login")
async def login(request: Request):
    if not OAUTH_CLIENT_ID:
        raise HTTPException(501, "OAuth not configured (OAUTH_CLIENT_ID missing)")
    state = secrets.token_urlsafe(16)
    url = (
        f"{HF_AUTH_URL}"
        f"?client_id={OAUTH_CLIENT_ID}"
        f"&redirect_uri={_redirect_uri(request)}"
        f"&response_type=code"
        f"&scope=openid+profile"
        f"&state={state}"
    )
    resp = RedirectResponse(url=url)
    resp.set_cookie(
        "oauth_state",
        state,
        httponly=True,
        samesite="none",
        secure=True,
        max_age=600,
    )
    return resp


@app.get("/callback")
async def callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
):
    if error:
        return RedirectResponse("/?error=oauth_failed")
    if not code:
        raise HTTPException(400, "Missing authorization code")

    stored = request.cookies.get("oauth_state")
    if not state or not stored or state != stored:
        raise HTTPException(400, "OAuth state mismatch")

    async with httpx.AsyncClient() as client:
        tok_resp = await client.post(
            HF_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(request),
                "client_id": OAUTH_CLIENT_ID,
                "client_secret": OAUTH_CLIENT_SECRET,
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
        tok = tok_resp.json()
        access_token = tok.get("access_token")
        if not access_token:
            raise HTTPException(400, f"Token exchange failed: {tok}")

        info = await client.get(
            HF_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        userinfo = info.json()

    username = (
        userinfo.get("preferred_username")
        or userinfo.get("name")
        or userinfo.get("sub")
    )
    if not username:
        raise HTTPException(400, "Could not determine username from HuggingFace")

    session_tok = signer.dumps({"username": username})
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(
        "hf_session",
        session_tok,
        httponly=True,
        samesite="none",
        secure=True,
        max_age=86400 * 7,
    )
    resp.delete_cookie("oauth_state")
    return resp


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/")
    # Attributes must match how the cookie was set in /callback
    # (samesite="none", secure=True) or some browsers refuse the deletion.
    resp.delete_cookie("hf_session", samesite="none", secure=True)
    return resp


# ── Sheet fetch + row parsing (shared by auth and guest endpoints) ─

def _fetch_sheet_rows():
    """Return (rows, error). rows is [] when the sheet is unreachable."""
    try:
        ws = _worksheet()
        rows = ws.get_all_values()
        return rows, ""
    except Exception as exc:
        print(f"ERROR: Failed to fetch from Google Sheets API: {exc}", flush=True)
        return [], str(exc)


def _parse_weeks(rows: list, score_identities: list) -> tuple:
    """Parse sheet rows into week dicts.

    score_identities is a priority-ordered list of column-header names to
    try for the per-user score column (e.g. [username] for a student,
    ["GUEST", "default"] for guest mode). Returns (weeks_out, user_col_found).
    """
    headers = rows[0]

    def col(name: str) -> Optional[int]:
        for i, h in enumerate(headers):
            if h.strip().lower() == name.strip().lower():
                return i
        return None

    week_i  = col("Week")                if col("Week")                is not None else 0
    theme_i = col("Theme")               if col("Theme")               is not None else 1
    obj_i   = col("Learning objectives") if col("Learning objectives") is not None else 2
    max_i   = col("Max Points")          if col("Max Points")          is not None else 3
    admin_i = col("Admin Step")          if col("Admin Step")          is not None else 4

    # Score column: first identity that matches a header wins.
    user_col: Optional[int] = None
    for ident in score_identities:
        if not ident:
            continue
        user_col = col(ident)
        if user_col is not None:
            break

    def cell(row: list, idx: Optional[int], default: str = "") -> str:
        if idx is None or idx >= len(row):
            return default
        return row[idx].strip()

    def safe_int(s: str) -> Optional[int]:
        try:
            return int(float(s)) if s else None
        except (ValueError, TypeError):
            return None

    weeks_out = []
    for row in rows[1:]:
        if not any(c.strip() for c in row):
            continue

        max_pts    = safe_int(cell(row, max_i,   "0")) or 0
        admin_step = safe_int(cell(row, admin_i, "0")) or 0
        user_score = safe_int(cell(row, user_col)) if user_col is not None else None

        weeks_out.append({
            "week":       cell(row, week_i),
            "theme":      cell(row, theme_i),
            "objectives": cell(row, obj_i),
            "max_points": max_pts,
            "admin_step": admin_step,
            "user_score": user_score,
        })

    return weeks_out, user_col is not None


def _mock_fallback(username: str, reason: str, guest: bool = False):
    mock = [dict(w) for w in MOCK_WEEKS]   # shallow copy so originals stay clean
    payload = {
        "username": username,
        "weeks": mock,
        "user_col_found": False,
        "fallback": True,
        "fallback_reason": reason or "Sheet returned no data",
    }
    if guest:
        payload["guest"] = True
    return JSONResponse(payload)


# ── API ──────────────────────────────────────────────────────────

@app.get("/api/syllabus-data")
async def syllabus_data(request: Request):
    username = _current_user(request)

    # Require auth unless OAuth is not configured (local dev).
    if not username and OAUTH_CLIENT_ID:
        raise HTTPException(401, "Not authenticated")

    rows, sheet_error = _fetch_sheet_rows()
    if sheet_error or not rows:
        return _mock_fallback(username or "dev", sheet_error)

    weeks_out, user_col_found = _parse_weeks(rows, [username])

    return JSONResponse({
        "username":      username or "dev",
        "weeks":         weeks_out,
        "user_col_found": user_col_found,
    })


@app.get("/api/guest-data")
async def guest_data():
    """Public endpoint — live sheet content, guest score column.

    Uses the exact same fetch and row-parsing logic as the authenticated
    endpoint, but resolves scores from a dedicated "GUEST" (or "default")
    column header instead of a personal username column. If no such column
    exists, all user_score values are null and the map renders scoreless.
    MOCK_WEEKS is only used when the sheet itself is unreachable.
    """
    rows, sheet_error = _fetch_sheet_rows()
    if sheet_error or not rows:
        return _mock_fallback("Guest", sheet_error, guest=True)

    weeks_out, user_col_found = _parse_weeks(rows, ["GUEST", "default"])

    return JSONResponse({
        "username":      "Guest",
        "weeks":         weeks_out,
        "user_col_found": user_col_found,
        "guest":         True,
    })


# ── Frontend ─────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


if os.path.isdir("assets"):
    app.mount("/assets", StaticFiles(directory="assets"), name="assets")
