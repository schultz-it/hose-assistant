# HANDOFF.md — Project Progress & Continuation Guide

**Read this first, then read SPEC.md in full.** This file documents everything decided and done so far, so development can continue from Claude Code without losing context.

## What this project is

**Hose Assistant** — a public, open-source Home Assistant **add-on** (not a HACS integration) for smart irrigation: it calculates watering needs (FAO-56 ET₀ water-balance model) AND actuates the valves, with its own mobile-first tabbed web UI served via HA Ingress. Full specification: `SPEC.md` (v1.0, complete and implementation-ready).

## Key decisions already made (do not re-litigate)

1. **Add-on, not Lovelace/HACS.** Evaluated and rejected the helpers+automations route: too much structured state (unlimited zones × ~20 params × programs), no real "add zone" concept, UI limitations, not distributable. Hybrid model adopted instead: add-on is the brain + key state exposed back to HA as native entities (SPEC §11, Milestone 8).
2. **Stack:** Python 3.12 + FastAPI + APScheduler + SQLite (in `/data`) backend; Preact + Tailwind (Vite) frontend; `astral` for sun data.
3. **Weather:** Open-Meteo (free, keyless) — provides precomputed FAO-56 ET₀, rain history/forecast, elevation from lat/long, and 10-year climate normals (used by the program generator). HA weather entities / local sensors are optional overrides only.
4. **Name:** "Hose Assistant" — a pun on Home Assistant (same "HA" initials). Verified available July 2026: no existing HA add-on/integration/product with this name; the irrigation solutions that exist go by other names (Irrigation Unlimited, Smart Irrigation, Rachio, etc.). GitHub repo slug: `hose-assistant`; add-on slug: `hose_assistant`. (Previously codenamed "Petrichor".)
5. **Program Generator is dual-engine:** rule-based (always available, offline, also powers the first-run wizard) + optional AI (via HA conversation agent or direct Anthropic/OpenAI key from add-on options). **Hard rule: AI output is always a proposal requiring user approval; AI never actuates valves.**
6. **Safety:** watchdog turn-off job persisted for every valve open; close-all on startup; abort+close-all if HA API unreachable; per-zone max runtime cap.
7. **4 default programs:** Lawn Start (fixed mode, short frequent runs, auto-expires), Spring, Summer, Autumn (budget/ET mode). Season boundaries derived from local climate normals, not fixed dates.
8. **Global "Watering Intensity" slider** Low→Extreme = 0.5×–2.0× multiplier, applied live.
9. **i18n:** English is the source language for app + docs; `it.json` ships as first translation.

## Current state of the repository (what exists right now)

```
hose-assistant/                    ← repo root, ready to publish on GitHub
├── HANDOFF.md                     ← this file
├── SPEC.md                        ← full spec v1.0 (13 sections) — THE reference
├── README.md                      ← user-facing readme (replace YOUR_GITHUB_USERNAME)
├── LICENSE                        ← MIT
├── .gitignore
├── repository.yaml                ← HA add-on repository manifest (replace YOUR_GITHUB_USERNAME)
├── .github/workflows/build.yaml   ← multi-arch build via home-assistant/builder
└── hose_assistant/                ← the add-on
    ├── config.yaml                ← manifest: ingress on 8099, hassio_api, homeassistant_api, options schema
    ├── build.yaml                 ← HA base images (alpine 3.19) for aarch64/amd64 (armv7 dropped by HA in 2026)
    ├── Dockerfile                 ← installs python3 + requirements, copies backend/frontend/rootfs
    ├── DOCS.md                    ← stub
    ├── CHANGELOG.md               ← 0.1.0
    ├── rootfs/etc/services.d/hose_assistant/run  ← s6 start script (bashio, exports options as env vars)
    ├── backend/
    │   ├── requirements.txt       ← fastapi, uvicorn, httpx
    │   ├── __init__.py
    │   └── main.py                ← MILESTONE 1 skeleton: hello page, /api/health,
    │                                /api/ha/entities?domain= (Supervisor API proof)
    └── frontend/dist/.gitkeep     ← placeholder; frontend not started
```

**Milestone status:**
- ✅ **Milestone 1** (skeleton) — tested OK on Andrea's HA (Ingress hello page + Supervisor API entity listing both work; relative-URL routing under Ingress confirmed).
- ✅ **Milestone 2** (data layer) — SQLite in `/data` + SQLAlchemy models + CRUD API for config/zones/programs. Verified locally (34/34 checks) AND confirmed on Andrea's HA (0.2.1 installed, JSON endpoints respond). Note: 0.2.1 also dropped armv7 (32-bit removed by HA/builder in 2026) and fixed CI (builder needs explicit `--image`); GitHub Actions builds are green for aarch64+amd64.
- ✅ **Milestone 3** (weather + sun) — Open-Meteo client (`core/weather.py`: daily ET₀ + rain, past+forecast; elevation API), `core/sun.py` (astral), `core/kc.py` (monthly Kc tables × shade factor; `shade_fine` 0–100 → factor 1.0→0.5, preset sets slider default, so Zone default `shade_fine` is now 0). Endpoints: `GET /api/weather/summary`, `GET /api/balance`, `POST /api/balance/refresh` (upserts et0/rain/kc_eff per enabled zone per past day; deficit left to M4). Elevation auto-fetched on config PUT when lat/long set. Temp dev page has a location form + refresh button. Verified locally with real Open-Meteo (29/29 checks) AND confirmed on Andrea's HA (0.3.0: location saved, elevation 260 m, tz Europe/Rome, sun + 14-day ET₀/rain data OK).
- ✅ **Milestone 4** (engine + executor) — `core/engine.py` (deficit chain, MAD trigger, runtime, cycle&soak, window packing + proportional reduction, program selection incl. wrap-around date ranges + priority, fixed-mode planning), `core/executor.py` (sequential sessions, master valve, watchdog-before-open, close-all on startup/error/stop), `core/scheduler.py` (APScheduler, SQLite job store `/data/scheduler.db`, daily_calc cron + execute_plan date job), `core/ha.py` (Supervisor client, valve/switch/input_boolean domains), `core/soil.py`. Endpoints: schedule/skip/run zone/run program/stop_all/engine recalc/log. Verified locally 38/38 (engine math incl. storm-infiltration clamp, executor with mocked HA incl. HA-failure abort, stop_all, master sequencing, watchdog persistence). Version 0.4.1 (adds zone add/delete + entity autocomplete on the dev page). **Confirmed on Andrea's HA with input_boolean mock valve: zone ran and auto-closed.** Known M4 simplifications: no zone interleaving during soaks (sequential cycles), manual-valve-change detection via WS subscription not yet implemented (watchdogs cover safety), moisture/rain-sensor skip checks not yet wired into planning (fields exist).
- ✅ **Milestone 5 (first pass)** (web UI) — Preact + Tailwind v4 (Vite, `base:''` for Ingress) SPA in `hose_assistant/frontend/`; **built `dist/` is committed** (Dockerfile copies it; no node in the image). Tabs: Dashboard (status, intensity slider, reservoir bars, upcoming+skip, run/recalc/stop, log, 5s polling), Zones (editor with presets), Setup (first-run default tab when no location), Programs (read-only until M6). Backend: `GET /api/status`, SPA served by StaticFiles mount at `/` (API + `/dev` win), dev page moved to `/dev`. i18n: `t()` + `en.json`. Validated in a local browser preview (desktop+mobile, incl. live elevation fetch, zone editor presets, run→abort failsafe path). Rebuild: `cd hose_assistant/frontend && npm install && npm run build`. Version 0.5.0. **Pending test on Andrea's HA.** M5 leftovers for later: Tab 3 programs editor (M6), WebSocket live updates (poll for now), countdown ring, drag reorder of zones, map-pin location picker.
- Milestones 6–10 not started (see SPEC §12).

**Repo published (2026-07-08):** public at **https://github.com/schultz-it/hose-assistant**, default branch `main`. Git identity: Andrea Brunelli <andrea@imballaggibrunelli.it>. `gh` CLI authenticated as `schultz-it` (scopes incl. `repo`, `workflow`) with git credential helper configured.

**Local dev/test setup:** system `python3` is 3.9 (too old for `X | None` runtime annotations); use `/opt/homebrew/bin/python3.11` for a venv. Set `DATA_DIR` env var to point the SQLite DB at a writable folder outside `/data` when testing off-HA. A verification script lives in the session scratchpad (`verify_m2.py`).

## Immediate next steps (in order)

1. ~~Publish the repo~~ — ✅ done.
2. ~~Test Milestone 1 on HA~~ — ✅ done.
3. **Re-test Milestone 2 on HA**: in HA, update/reinstall the add-on (Settings → Add-ons → Hose Assistant → rebuild/update), start it, open the panel → the hello page now shows **config · zones · programs** links; clicking each should return JSON (`config` = the singleton, `zones`/`programs` = `[]` until created). Remaining M1 ingress note still open but low-risk: `uvicorn --root-path` handling may be needed once the real SPA generates absolute URLs (revisit in Milestone 5).
4. **Then proceed milestone by milestone** (SPEC §12): 3 weather+sun → 4 engine+executor (test with `input_boolean` mock valves, keep them for days before touching real valves) → 5 UI tabs 1/2/4 → 6 rule-based generator + wizard → 7 intensity/overrides/rain delay/off → 8 HA entity exposure → 9 AI generator → 10 i18n/docs/release.

## Working conventions

- One milestone at a time; do not implement ahead of the current milestone.
- The developer (Andrea) is a non-developer: give step-by-step, copy-paste-ready instructions, exact file paths, and explain how to test each milestone on his HA instance.
- All code, comments, UI strings and docs in **English**; conversation can be in Italian.
- Keep SPEC.md as the single source of truth; if a design change is agreed, update SPEC.md in the same commit.
