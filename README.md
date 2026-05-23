---
title: NTU MARA Quest
emoji: 🗺️
colorFrom: green
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
hf_oauth: true
---

# NTU MARA Quest

A gamified course syllabus viewer for the NTU MARA Database & Programming course. Authenticate with your HuggingFace account to see your personal progress on an interactive 8-bit overworld map.

## Environment Variables

Set these in your HuggingFace Space secrets:

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | ✅ | Full JSON string of your Google service account key |
| `GOOGLE_SHEET_ID` | ✅ | The ID portion of your Google Sheet URL |
| `GOOGLE_SHEET_TAB` | optional | Sheet tab name (default: `Sheet1`) |
| `APP_SECRET_KEY` | recommended | Random secret for signing session cookies |
| `OAUTH_CLIENT_ID` | ✅ (auto) | Injected by HF when `hf_oauth: true` |
| `OAUTH_CLIENT_SECRET` | ✅ (auto) | Injected by HF when `hf_oauth: true` |

## Google Sheet Format

The sheet must have this column layout:

| A: Week | B: Theme | C: Learning objectives | D: Max Points | E: Admin Step | F+: [HF Username] |
|---|---|---|---|---|---|
| Week 1 | Intro to SQL | Objective 1\nObjective 2 | 3 | 1 | 2 |
| Week 2 | Joins | ... | 2 | 1 | 1 |

- **Admin Step** = `1` unlocks the node (green), `0` keeps it greyed out
- **Max Points** = max score for the week (≤5 shows stars, >5 shows numerical)
- Student columns use HuggingFace usernames as headers
