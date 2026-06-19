# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NTU MARA Quest is an interactive course-progress visualizer for a 13-week database and programming course. It consists of:

- **`main.py`** — FastAPI backend: HuggingFace OAuth login, Google Sheets score fetching, session cookies
- **`static/index.html`** — the served frontend: a `<canvas>`-based animated quest map with per-node progress modals
- **`assets/`** — static images and SVGs served at `/assets/*`

> **Note:** The root-level `index.html` is an orphaned prototype (Tailwind/VT323 pan-zoom DOM app) that is NOT served by the backend. Do not edit it — edit `static/index.html`.

## Running the Project

The backend must be running for OAuth and score data to work:

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 7860
# then open http://localhost:7860
```

Environment variables needed for full functionality (optional for local dev):

| Variable | Purpose |
|---|---|
| `OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` | HuggingFace OAuth |
| `APP_SECRET_KEY` | Stable secret for signing session cookies |
| `GOOGLE_SHEET_ID` | Google Sheet containing student scores |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Service-account credentials JSON (stringified) |
| `GOOGLE_SHEET_TAB` | Sheet tab name (default: `Sheet1`) |

Without OAuth configured, `/api/syllabus-data` works without auth. Without Sheets configured, the app falls back to `MOCK_WEEKS`.

## Architecture

### Backend (`main.py`)

- **OAuth flow** — `/login` → HuggingFace → `/callback` → signed `hf_session` cookie via `itsdangerous.URLSafeSerializer`
- **`_current_user(request)`** — reads `X-HF-Username`/`X-HF-User-Id`/`X-HF-User` headers (HF Space injection) or the `hf_session` cookie
- **`/api/syllabus-data`** — fetches the Google Sheet, finds the user's score column by HF username, returns per-week scores; falls back to `MOCK_WEEKS` on any Sheets error
- **`/api/guest-data`** — public endpoint returning `MOCK_WEEKS` with no scores
- **`MOCK_WEEKS`** — 14-entry list used as fallback and for guest mode

### Frontend (`static/index.html`)

- **`NODES` array** — source of truth for all 14 course nodes; each has `id`, zone, canvas `x`/`y`, and week label
- **Canvas render loop** — `tick()` calls `nodes()` + `drawPaths()` every frame; pan/zoom state in `camX`/`camY`/`zoom`
- **`weekData(i)`** — maps node index → sheet row; called per node per frame (optimization opportunity: memoize)
- **`openModal(id)`** — builds and displays the per-node progress modal

## Making Changes

**Adding a course node** — add an entry to `NODES` in `static/index.html` with `id`, `zone`, `x`/`y` canvas coordinates, and `week` label.

**Editing week content** — update `MOCK_WEEKS` in `main.py` (used for guest mode and fallback); the authoritative content lives in the Google Sheet.

**Styling** — the aesthetic uses Press Start 2P (Google Fonts) and NES.css for pixel-art UI. Zone palettes are hard-coded in `drawMainSegment`/`drawBranchSegment`.

## Testing

**Run all tests before and after every code change:**

```bash
python -m pytest tests/ -v
```

All 49 tests must pass. Never push code that breaks the test suite.

### Test structure

| File | Coverage |
|---|---|
| `tests/test_unit.py` | Pure helpers: `col()`, `cell()`, `safe_int()`, `_current_user()`, `MOCK_WEEKS` shape |
| `tests/test_integration.py` | HTTP routes: `/`, `/api/guest-data`, `/api/syllabus-data`, `/login`, `/logout`, `/callback` CSRF |

### Writing new tests

- Add unit tests for any new pure-Python helper added to `main.py`
- Add integration tests for any new route or changed response shape
- Use `unittest.mock.patch("main.<symbol>")` to mock env vars and `_worksheet()`
- Tests must not make real network calls (Google Sheets, HuggingFace)
- A zero user score (`user_score=0`) must remain distinguishable from `None` — the `test_zero_user_score_preserved` test guards this

### Installing test dependencies

```bash
pip install pytest pytest-asyncio
```
