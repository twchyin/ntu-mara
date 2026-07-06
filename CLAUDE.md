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
- **`/api/guest-data`** — public endpoint; fetches the live sheet with the same parsing pipeline, resolving scores from a `GUEST` (or `default`) column header; falls back to `MOCK_WEEKS` only when the sheet is unreachable
- **`MOCK_WEEKS`** — 14-entry list used as the unreachable-sheet fallback for both endpoints

### Frontend (`static/index.html`)

- **`NODES` array** — source of truth for all 14 course nodes; each has `id`, `label`, `type` (`'week'`/`'quiz'`), `dataIndex`, and world `x`/`y` (quiz nodes also carry `isBranch`/`branchFrom`); `NODE_META` holds per-node design copy (title/island/about/stars)
- **Layered world** — a pannable/zoomable `#map-frame` contains `#world` (1000×600, CSS `transform`): canvas (background art + roaming snake) → `#trail` SVG (animated dashed paths, rebuilt by `renderTrail()`) → `#deco-layer` (CSS-animated dust/fireflies/cacti/sparks) → `#node-layer` (DOM `.node-card` buttons, rebuilt by `buildNodeCards()`) → `#player-sprite` emoji
- **Render loop** — `tick()` only draws the snake on canvas; guarded by `startLoop()`/`stopLoop()` so only one rAF loop ever runs. All other animation is CSS keyframes
- **`nodeStatus(i)`** — maps progress data into `done`/`current`/`locked` for card styling and trail colors
- **`weekData(i)`** — maps node index → sheet row by label search; memoized in `weekDataCache`, reset via `invalidateWeekData()` whenever `weeks` is reassigned
- **`openModal(idx)`** — biome-themed (`data-theme`) modal; every node uses the same layout: status pill + about + mastery stars (sheet objectives, falling back to `NODE_META.stars`)

## Making Changes

**Adding a course node** — add an entry to `NODES` in `static/index.html` with `id`, `label`, `type`, `dataIndex`, and `x`/`y` canvas coordinates (plus `isBranch`/`branchFrom` for quiz branches).

**Editing week content** — update `MOCK_WEEKS` in `main.py` (used for guest mode and fallback); the authoritative content lives in the Google Sheet.

**Styling** — the aesthetic uses Press Start 2P (HUD), VT323 (modal titles), and JetBrains Mono (modal body) from Google Fonts, plus NES.css for the login screen. Node-status palettes live in the `.node-card[data-status=…]` CSS rules; trail zone tints in `renderTrail()`; modal biome palettes in the `#modal-box[data-theme=…]` CSS variables.

## Testing

**Run all tests before and after every code change:**

```bash
python -m pytest tests/ -v
```

All 50 tests must pass. Never push code that breaks the test suite.

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
