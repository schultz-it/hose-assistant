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
    ├── build.yaml                 ← HA base images (alpine 3.19) for aarch64/amd64/armv7
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

**Milestone status: Milestone 1 is scaffolded but NOT yet tested on a real HA instance.** Everything else (Milestones 2–10, see SPEC §12) is not started.

**Repo published (2026-07-08):** public at **https://github.com/schultz-it/hose-assistant**, default branch `main`, initial commit `Initial scaffold: Milestone 1 skeleton`. Git identity: Andrea Brunelli <andrea@imballaggibrunelli.it>. `gh` CLI authenticated as `schultz-it` (scopes incl. `repo`, `workflow`) with git credential helper configured.

## Immediate next steps (in order)

1. ~~**Publish the repo**~~ — ✅ done. Repo live at https://github.com/schultz-it/hose-assistant.
2. **Test Milestone 1 on HA**: add the GitHub repo URL in HA (Settings → Add-ons → Repositories), install Hose Assistant, start it, open the sidebar panel → expect the hello page; click "Test Supervisor API" → expect a JSON list of `switch.*` entities.
   - Faster dev loop alternative: copy the `hose_assistant/` add-on folder into HA's `/addons` local directory via Samba and use "Local add-ons".
3. **Known Milestone 1 gaps to close before calling it done**:
   - Ingress path handling: the SPA/API must work under the HA-proxied path (honor `X-Ingress-Path`, use relative URLs). The current hello page uses a relative link — verify it works via Ingress.
   - `uvicorn` root behavior behind Ingress may need `--root-path` handling.
4. **Then proceed milestone by milestone** (SPEC §12): 2 data layer → 3 weather+sun → 4 engine+executor (test with `input_boolean` mock valves, keep them for days before touching real valves) → 5 UI tabs 1/2/4 → 6 rule-based generator + wizard → 7 intensity/overrides/rain delay/off → 8 HA entity exposure → 9 AI generator → 10 i18n/docs/release.

## Working conventions

- One milestone at a time; do not implement ahead of the current milestone.
- The developer (Andrea) is a non-developer: give step-by-step, copy-paste-ready instructions, exact file paths, and explain how to test each milestone on his HA instance.
- All code, comments, UI strings and docs in **English**; conversation can be in Italian.
- Keep SPEC.md as the single source of truth; if a design change is agreed, update SPEC.md in the same commit.
