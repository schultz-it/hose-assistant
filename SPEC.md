# Hose Assistant — Smart Irrigation Add-on for Home Assistant

> *Home Assistant runs your house. Hose Assistant runs your garden.*

**Project specification v1.0 — implementation-ready document for AI-assisted development (Claude Code).**

---

## 1. Project Overview

Hose Assistant is a **Home Assistant add-on** (not a HACS integration) that calculates, schedules and executes lawn/garden irrigation based on real evapotranspiration data, weather forecasts, soil/grass/shade characteristics and user-defined seasonal programs. It both **computes** watering needs (like "Smart Irrigation") and **actuates** valves (like "Irrigation Unlimited") — with its own polished, mobile-first web UI served through HA Ingress.

### Goals
- Zero-friction install: add repo → install → open UI → 5-minute setup wizard.
- Works 100% offline-capable in its core logic (weather via free Open-Meteo API, no API key required).
- Public, open-source, fully documented in English, translatable (i18n).
- Deterministic and safe: hard failsafes on every valve actuation; AI features are optional and never control hardware directly.

### Non-goals (v1)
- No drip-fertigation dosing, no flow-meter leak detection (roadmap items).
- No standalone mode outside Home Assistant.

---

## 2. Architecture

```
┌─────────────────────────── HA Add-on container ───────────────────────────┐
│                                                                            │
│  FastAPI backend (Python 3.12)                                             │
│  ├── REST API  (/api/...)  + WebSocket (/ws) for live dashboard updates    │
│  ├── APScheduler: daily recalc job, program runs, cycle&soak timers        │
│  ├── Engine: water-balance model, schedule builder                         │
│  ├── Program Generator: rule-based + optional AI backend                   │
│  ├── HA client: Supervisor API (http://supervisor/core/api) with           │
│  │   SUPERVISOR_TOKEN (automatic, zero user config)                        │
│  ├── Weather client: Open-Meteo (forecast + archive + elevation APIs)      │
│  ├── Sun: `astral` library (sunrise/sunset/solar position from lat/long)   │
│  └── SQLite in /data/hose_assistant.db (persists across updates)           │
│                                                                            │
│  Frontend: Preact + Tailwind SPA, served statically by FastAPI             │
│  └── 4 tabs, i18n JSON files, mobile-first, HA Ingress compatible          │
└────────────────────────────────────────────────────────────────────────────┘
```

### Key technology decisions
| Concern | Choice | Why |
|---|---|---|
| Distribution | HA add-on repository (GitHub) | Two-click install, Ingress UI, auto-updates |
| Backend | Python 3.12 + FastAPI + uvicorn | Async, small, familiar to HA ecosystem |
| Scheduler | APScheduler (SQLAlchemy job store on /data) | Survives restarts, cron + date triggers |
| DB | SQLite via SQLAlchemy | Single file in /data, zero admin |
| Weather/ET₀ | **Open-Meteo** | Free, keyless, returns **FAO-56 ET₀ precomputed**, rain history/forecast, and elevation from lat/long |
| Sun data | `astral` | Offline sunrise/sunset/azimuth/elevation |
| Frontend | Preact + Tailwind (Vite build) | Tiny bundle, fast on mobile, easy vibecoding |
| i18n | JSON message catalogs, `en.json` as source of truth | Community translations via PR |
| HA control | Supervisor proxy API | No long-lived token needed from the user |

---

## 3. Repository Structure (HA add-on repo)

```
hose-assistant/                     # repository root (also the add-on repo)
├── repository.yaml                 # name, url, maintainers
├── README.md                       # user-facing: what it is, screenshots, install
├── hose_assistant/                 # the add-on itself
│   ├── config.yaml                 # add-on manifest (see §4)
│   ├── Dockerfile
│   ├── DOCS.md                     # in-HA documentation page
│   ├── CHANGELOG.md
│   ├── icon.png  logo.png          # 128x128 / 256x* branding
│   ├── rootfs/
│   │   └── etc/services.d/hose_assistant/run   # s6 service start script
│   ├── backend/
│   │   ├── main.py                 # FastAPI app, Ingress-aware root path
│   │   ├── api/                    # routers: setup, zones, programs, engine, dashboard, ai
│   │   ├── core/
│   │   │   ├── engine.py           # water balance + schedule builder
│   │   │   ├── executor.py         # valve actuation, sequencing, failsafes
│   │   │   ├── generator_rules.py  # rule-based program generator
│   │   │   ├── generator_ai.py     # AI program generator (optional)
│   │   │   ├── weather.py          # Open-Meteo client + HA sensor overrides
│   │   │   ├── sun.py              # astral wrapper
│   │   │   └── ha.py               # Supervisor API client (states, services)
│   │   ├── models/                 # SQLAlchemy + Pydantic schemas
│   │   └── i18n/                   # en.json, it.json, ...
│   └── frontend/
│       ├── src/
│       │   ├── App.jsx             # tab shell
│       │   ├── tabs/Setup.jsx  Zones.jsx  Programs.jsx  Dashboard.jsx
│       │   ├── components/         # sliders, cards, gauges, entity pickers
│       │   └── i18n/               # mirrors backend catalogs
│       └── vite.config.js
└── .github/workflows/build.yaml    # multi-arch image build (aarch64, amd64, armv7)
```

---

## 4. Add-on Manifest (`config.yaml`)

```yaml
name: Hose Assistant
version: "1.0.0"
slug: hose_assistant
description: Smart irrigation calculator & controller — ET-based, weather-aware, AI-assisted.
url: https://github.com/<owner>/hose-assistant
arch: [aarch64, amd64, armv7]
init: false
ingress: true
ingress_port: 8099
panel_icon: mdi:sprinkler-variant
panel_title: Hose Assistant
hassio_api: true
homeassistant_api: true
map:
  - addon_config:rw
options:
  log_level: info
  ai_provider: "none"          # none | ha_conversation | anthropic | openai
  ai_api_key: ""               # only for direct providers
schema:
  log_level: list(debug|info|warning|error)
  ai_provider: list(none|ha_conversation|anthropic|openai)
  ai_api_key: str?
```

All functional configuration lives in the **web UI**, not in add-on options. Options hold only infrastructure-level settings (logging, AI provider credentials).

---

## 5. Data Model

All units metric internally; UI converts if user selects imperial.

### 5.1 SystemConfig (singleton)
| Field | Type | Notes |
|---|---|---|
| latitude, longitude | float | required; drives everything |
| elevation_m | float | auto-fetched from Open-Meteo Elevation API, editable |
| timezone | str | default from HA config |
| units | enum `metric/imperial` | display only |
| weather_entity | str? | optional HA `weather.*` entity to blend with Open-Meteo |
| master_valve_entity | str? | optional pump/master `switch.*` — opened before any zone, closed after |
| master_valve_pre_open_s | int | default 5 |
| daily_calc_time | time | default 03:00 — when the engine recomputes today's plan |
| watering_intensity | float 0.5–2.0 | the global slider (Low=0.5 … Normal=1.0 … Extreme=2.0); applied live |
| system_enabled | bool | master ON/OFF |
| rain_delay_until | datetime? | 24/48/72h pause |
| forecast_rain_skip_mm | float | default 5 mm/24h forecast → skip |
| wind_skip_kmh | float? | optional; skip spray zones above threshold |
| language | str | UI locale |

### 5.2 Zone
| Field | Type | Notes |
|---|---|---|
| id, name, icon | | icon = MDI name |
| valve_entity | str | required — `switch.*` or `valve.*` |
| enabled | bool | |
| order | int | sequencing position |
| irrigation_type | enum | `spray` (default PR 35 mm/h) · `rotor` (15) · `mp_rotator` (10) · `drip` (6) |
| precipitation_rate_mmh | float | prefilled from type, editable |
| soil_type | enum | `sandy` (AWC 0.06 mm/mm, infil 25 mm/h) · `loam` (0.12, 12) · `clay` (0.17, 4) |
| grass_type | enum | `cool_season` (Kc table peaks 0.95, root 15 cm) · `warm_season` (peaks 0.75, root 20 cm) · `shrubs_drip` |
| root_depth_cm | float | prefilled, editable |
| area_m2 | float? | optional; enables water-volume reporting |
| slope | enum `flat/gentle/steep` | steep ⇒ auto cycle & soak |
| **shade_preset** | enum | `full_sun` (factor 1.0) · `partial` (0.8) · `shade` (0.6) |
| shade_fine | int 0–100 | fine slider mapped 1.0→0.5 around the preset |
| shade_monthly | float[12]? | advanced: per-month shade factor (a house's shadow in June ≠ October) |
| moisture_entity | str? | optional soil-moisture sensor |
| moisture_skip_pct | float? | skip zone if reading above threshold |
| rain_sensor_entity | str? | optional binary sensor; ON ⇒ skip |
| max_runtime_min | int | hard cap per session (failsafe), default 60 |

**Effective crop coefficient**: `Kc_eff = Kc_month(grass) × shade_factor(month)`.

### 5.3 Program (the 4 seasonal modes; user can add more)
| Field | Type | Notes |
|---|---|---|
| id, name, icon, color | | defaults: **Lawn Start**, **Spring**, **Summer**, **Autumn** |
| mode | enum | `budget` (ET water-balance) · `fixed` (Lawn Start: fixed short frequent runs) |
| date_start, date_end | month-day | or `manual_only: bool` |
| priority | int | resolves overlapping date ranges |
| allowed_days | weekday set / `every_n_days` | |
| window_start, window_end | time | e.g. Summer 04:00–08:00 (pre-dawn) |
| mad_pct | float | Management Allowed Depletion — how dry before watering (e.g. 50%) |
| et_multiplier | float | seasonal tuning, default 1.0 |
| zone_overrides | map | per-zone enable/disable, runtime multiplier |
| fixed_runs | list | only for `fixed` mode: `[{time, minutes_per_zone}]` |
| generated_by | enum `manual/rules/ai` | badge in UI; flips to `manual` on edit |
| ai_explanation | str? | natural-language rationale stored with AI output |

### 5.4 Runtime tables
- `water_balance(zone_id, date, et0, kc_eff, rain_mm, irrigated_mm, deficit_mm)`
- `schedule(run_id, program_id, zone_id, start, duration_min, status: planned/running/done/skipped, skip_reason)`
- `event_log(ts, level, message, meta)`

---

## 6. Calculation Engine

Daily at `daily_calc_time` (and on any config change):

1. **Fetch weather**: Open-Meteo daily ET₀ (yesterday actual + 7-day forecast), precipitation history/forecast. If `weather_entity` or local rain sensors are set, local readings override remote precipitation.
2. **Update bucket per zone**:
   `deficit += ET₀ × Kc_eff × intensity_slider × program.et_multiplier − effective_rain − irrigation_applied`
   Effective rain = min(rain, infiltration capacity); deficit clamped to [0, AWC × root_depth].
3. **Trigger check** (budget mode): if `deficit ≥ MAD% × (AWC × root_depth)` → schedule the zone.
4. **Forecast skip**: if forecast rain next 24h ≥ `forecast_rain_skip_mm` → skip, log reason, re-evaluate tomorrow. Same for moisture-sensor threshold, rain sensor, wind (spray zones), rain delay, system off.
5. **Runtime**: `minutes = deficit_mm / precipitation_rate_mmh × 60`, capped at `max_runtime_min`.
6. **Cycle & soak**: if runtime × PR exceeds soil infiltration capacity (always for `steep`): split into cycles of `infiltration_mm / PR` minutes with soak pauses ≥ cycle length, interleaving other zones during soaks.
7. **Sequencing**: zones run strictly one at a time (plus master valve), ordered by `order`, packed into the program window. If total exceeds the window → proportional reduction + warning event.

### Executor & failsafes (non-negotiable)
- Every valve `turn_on` schedules an independent watchdog `turn_off` at `duration + 2 min` — even if the process restarts (job store persisted).
- On add-on start: close all known valves ("clean slate").
- If HA API is unreachable mid-run: abort session, close everything, log error.
- Manual valve changes from HA are detected (state subscription) and logged; a valve turned off externally marks the run `done`.

---

## 7. Program Generator

### 7.1 Rule-based (always available, offline-capable)
Inputs: lat/long → **Open-Meteo Climate/Archive API** (10-year monthly ET₀ & rain normals for the exact location), grass Kc tables, soil, shade.
Output: full proposed set of the 4 programs with:
- Season boundaries derived from local climate (Spring starts when 15-day mean ET₀ crosses ~2 mm/day, Summer ~4 mm/day, etc.), not fixed calendar dates.
- Windows: pre-dawn in Summer, morning in Spring/Autumn.
- MAD, `et_multiplier`, allowed days per climate zone.
- **Lawn Start**: fixed mode, 3–4 short daily runs (e.g. 07:00/12:00/17:00 × 5 min), duration prompts user for seeding date, auto-expires after 4–6 weeks into the season program.

Flow: **Generate → preview diff → user edits → Apply**. This generator is also the final step of the first-run wizard.

### 7.2 AI generator (optional)
- Providers: `ha_conversation` (uses the user's configured HA conversation agent via Supervisor API — zero extra keys) or direct `anthropic`/`openai` with API key from add-on options.
- Prompt bundle: full system/zone config, climate normals, current water-balance history, plus a **free-text notes field** ("lawn reseeded in September", "zone 3 pools water").
- The model must return JSON matching the Program schema (strict validation; retry once on invalid output; fall back to rule-based with a clear message).
- Stores `ai_explanation` and shows it in the UI.
- Extra feature: **"Ask AI to review"** on existing programs → suggestions comparing config vs. actual balance history.
- **Hard rule: AI output is always a proposal requiring explicit user approval. AI never actuates valves.**

---

## 8. Web UI — 4 Tabs

Mobile-first, bottom tab bar on small screens, MDI icons, dark/light following HA theme. All strings via i18n catalog.

### Tab 1 — Setup (mdi:cog)
First-run wizard (location → auto elevation/sun preview → weather entities → master valve) then editable form. Map-pin or lat/long input; live sunrise/sunset card as instant feedback.

### Tab 2 — Zones (mdi:sprinkler)
Card list with add/edit/reorder (drag). Zone editor: entity picker (autocomplete from HA `switch.*`/`valve.*`), type/soil/grass selectors with illustrated presets, shade preset + fine slider + optional monthly curve editor, optional sensors, live "estimated PR & runtime at current deficit" preview.

### Tab 3 — Programs (mdi:calendar-clock)
Cards for the 4 programs (badge: manual / rules / AI). Buttons: **Auto-generate** · **Generate with AI** (hidden if provider=none) · edit. Timeline strip showing which program covers which dates. AI explanation shown in an expandable panel.

### Tab 4 — Dashboard (mdi:view-dashboard) *(default tab after setup)*
- **Now**: active zone with countdown ring, or next planned run; live via WebSocket.
- **Watering Intensity slider** (Low → Extreme) — applies immediately to future calculations and, optionally, proportionally rescales today's remaining plan.
- **Soil reservoir bars** per zone (deficit vs. MAD threshold).
- **Upcoming schedule** list with per-run skip/edit (duration override of the generated plan).
- **Controls**: Run program now · Run single zone (minutes picker) · Rain delay 24/48/72h · **System OFF** master toggle · Stop everything (panic button).
- **Event log** (last 50, with skip reasons: "skipped — 8 mm rain forecast").

---

## 9. API Surface (internal, consumed by the SPA)

```
GET/PUT  /api/config                     GET      /api/ha/entities?domain=switch
CRUD     /api/zones                      GET      /api/weather/summary
CRUD     /api/programs                   GET      /api/balance
POST     /api/programs/generate          # {engine: rules|ai, notes?} → proposal
POST     /api/programs/apply             # apply a previewed proposal
GET      /api/schedule                   POST     /api/schedule/{run_id}/skip|override
POST     /api/run/program/{id}           POST     /api/run/zone/{id}?minutes=
POST     /api/system/off|on|rain_delay   POST     /api/stop_all
GET      /api/log                        WS       /ws   # state pushes
```

Ingress note: honor `X-Ingress-Path` header / relative URLs so the SPA works under the HA-proxied path.

---

## 10. i18n & Documentation

- Source language **English**: `en.json` in backend + frontend; keys like `zones.editor.shade_preset.partial`.
- Adding a language = one JSON file + PR; UI language picker in Setup; falls back to English for missing keys.
- Ship `it.json` as the first translation.
- **README.md**: pitch, screenshots, install (add repo URL → install → open), quick start.
- **DOCS.md** (shown inside HA): full parameter reference, how the water-balance model works (with the formula), FAQ, troubleshooting, privacy note (only lat/long sent to Open-Meteo; AI features send config data to the chosen provider only when explicitly invoked).

---

## 11. HA Entity Exposure (hybrid model)

Hose Assistant is the brain, but key state must be visible/usable in native HA (dashboards, automations, Recorder history):

- **Primary path — MQTT Discovery** (if the user has an MQTT broker; auto-detected via Supervisor services API): publish per-zone `sensor.hose_assistant_<zone>_deficit`, `sensor.hose_assistant_<zone>_next_run`, plus `sensor.hose_assistant_active_zone`, `sensor.hose_assistant_next_program`, and bidirectional `switch.hose_assistant_system_enabled` + `number.hose_assistant_intensity` (commands from HA update the add-on and vice versa).
- **Fallback — REST states**: if no MQTT broker, POST the same sensors to `/api/states/...` via Supervisor (read-only, refreshed on every engine tick). Documented limitation: not registry-persistent.
- Exposure is opt-in via a toggle in the Setup tab.

## 12. Milestones (suggested vibecoding order)

1. **Skeleton**: add-on boots, Ingress serves "hello", Supervisor API lists entities.
2. **Data layer**: models, CRUD API, SQLite.
3. **Weather + sun**: Open-Meteo client, elevation, ET₀ pull, balance table filling.
4. **Engine + executor**: schedule builder, valve actuation with failsafes (test with `input_boolean` mocks).
5. **UI tabs 1, 2, 4** minimal → then Tab 3.
6. **Rule-based generator + first-run wizard.**
7. **Intensity slider, overrides, rain delay, system off.**
8. **HA entity exposure** (MQTT discovery + REST fallback, §11).
9. **AI generator.**
10. **i18n, DOCS, README, screenshots, GitHub Actions multi-arch build, release.**

## 13. Roadmap (post-v1)
Flow meters & leak detection · fertigation · history charts · seasonal water-usage report · notification hooks (run started/skipped with reason).
