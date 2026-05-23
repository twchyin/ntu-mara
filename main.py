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
        raise HTTPException(503, "GOOGLE_SERVICE_ACCOUNT_JSON not set")
    if not GOOGLE_SHEET_ID:
        raise HTTPException(503, "GOOGLE_SHEET_ID not set")
    creds = Credentials.from_service_account_info(
        json.loads(GOOGLE_SERVICE_ACCOUNT_JSON), scopes=SCOPES
    )
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
    resp.set_cookie("oauth_state", state, httponly=True, samesite="lax", max_age=600)
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
    if state and stored and state != stored:
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
        samesite="lax",
        max_age=86400 * 7,
        secure=bool(os.environ.get("SPACE_HOST")),
    )
    resp.delete_cookie("oauth_state")
    return resp


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/")
    resp.delete_cookie("hf_session")
    return resp


# ── API ──────────────────────────────────────────────────────────

@app.get("/api/syllabus-data")
async def syllabus_data(request: Request):
    username = _current_user(request)

    # Require auth unless OAuth is not configured (local dev).
    if not username and OAUTH_CLIENT_ID:
        raise HTTPException(401, "Not authenticated")

    try:
        ws = _worksheet()
        rows = ws.get_all_values()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Sheet read error: {exc}") from exc

    if not rows:
        return JSONResponse({"username": username or "dev", "weeks": [], "user_col_found": False})

    headers = rows[0]

    def col(name: str) -> Optional[int]:
        for i, h in enumerate(headers):
            if h.strip().lower() == name.strip().lower():
                return i
        return None

    week_i = col("Week") if col("Week") is not None else 0
    theme_i = col("Theme") if col("Theme") is not None else 1
    obj_i = col("Learning objectives") if col("Learning objectives") is not None else 2
    max_i = col("Max Points") if col("Max Points") is not None else 3
    admin_i = col("Admin Step") if col("Admin Step") is not None else 4

    # Find the student's score column (case-insensitive match on HF username).
    user_col: Optional[int] = None
    if username:
        for i, h in enumerate(headers):
            if h.strip().lower() == username.strip().lower():
                user_col = i
                break

    def cell(row: list, idx: Optional[int], default: str = "") -> str:
        if idx is None or idx >= len(row):
            return default
        return row[idx].strip()

    weeks_out = []
    for row in rows[1:]:
        if not any(c.strip() for c in row):
            continue

        def safe_int(s: str) -> Optional[int]:
            try:
                return int(float(s)) if s else None
            except (ValueError, TypeError):
                return None

        max_pts = safe_int(cell(row, max_i, "0")) or 0
        admin_step = safe_int(cell(row, admin_i, "0")) or 0
        user_score = safe_int(cell(row, user_col)) if user_col is not None else None

        weeks_out.append({
            "week": cell(row, week_i),
            "theme": cell(row, theme_i),
            "objectives": cell(row, obj_i),
            "max_points": max_pts,
            "admin_step": admin_step,
            "user_score": user_score,
        })

    return JSONResponse({
        "username": username or "dev",
        "weeks": weeks_out,
        "user_col_found": user_col is not None,
    })


# ── Frontend ─────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


if os.path.isdir("assets"):
    app.mount("/assets", StaticFiles(directory="assets"), name="assets")
