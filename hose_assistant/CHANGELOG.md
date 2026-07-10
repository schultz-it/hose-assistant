# Changelog

## 1.2.1
- Fix: recalculating the plan (manually, automatically after a save, or at
  the nightly run) could start a run immediately if the program's watering
  window for today had already passed — e.g. marking a zone "empty" in the
  evening and hitting Recalculate would fire the valve right away instead
  of waiting for tomorrow's window. Planning now always rolls forward to
  the window's next occurrence when today's has closed, for both budget-mode
  windows and fixed-mode run times; a run is never scheduled outside its
  configured window.

## 1.2.0
- Auto-recalculate the plan after saving: creating/editing/deleting a zone,
  or applying a program set, now triggers the same weather -> deficit ->
  plan pipeline as the nightly run — no need to press "Recalculate plan"
  by hand anymore (the manual button is still there for whenever you want
  it, e.g. after a reservoir reset).
  - Best-effort: if the weather service is briefly unreachable, the save
    still succeeds and a warning is logged — it never blocks your edit.
  - Internally, the recalc pipeline (previously duplicated between the
    nightly cron and the manual endpoint) is now a single shared function.

## 1.1.3
- Reservoir reset now goes both ways: two small buttons per zone — 100%
  (just watered / rain the model missed) and 0% (bone dry: forces watering
  at the next plan). Both survive recomputes. API:
  POST /api/zones/{id}/reset_reservoir?state=full|empty.

## 1.1.2
- Fix: runs left "running" by an add-on restart or stop no longer linger as
  ghost entries in the dashboard (they showed as duplicate/stale upcoming
  runs). Interrupted runs are reconciled on startup and on STOP ALL.
- Upcoming runs now show the day and date (e.g. "Tuesday 16 February · 04:00",
  or Today/Tomorrow), localized to the chosen language.
- "Recalculate plan" now reports how many runs it planned (0 when the soil is
  already full — that is normal).

## 1.1.1
- Brianzöö: the local dialect of Brianza joins the language picker (10 total),
  lovingly translated — "FÈRMA TÜSS", "Aqua in de la tèra", "sütt".

## 1.1.0
- Seven more UI languages: French, German, Spanish, Portuguese, Chinese,
  Japanese and Arabic (now 9 total with English + Italian). Pick one in
  Setup → Language.
- Arabic renders right-to-left: the whole layout mirrors automatically.

## 1.0.3
- Backup & restore from the Setup tab: export all settings and history
  (config, zones, programs, water-balance, schedule, event log) to a JSON
  file, or restore from one (replaces current data; stops any running
  session first). New GET /api/backup, POST /api/restore.

## 1.0.2
- Reset soil reservoir per zone (↺ next to each reservoir bar): marks the
  zone as fully watered — useful after hand-watering or an unrecorded storm.
  Recorded as manual irrigation equal to the current deficit so the balance
  stays consistent across recomputes. New POST
  /api/zones/{id}/reset_reservoir.

## 1.0.1
- Brand identity: new icon and logo (white droplet with a negative-space
  house — Home Assistant living inside the water).
- Dashboard UX: the soil-reservoir bar now shows WATER LEFT (full = fine,
  empty = dry, blue fill) instead of the counter-intuitive deficit bar.

## 1.0.0 🎉
- First stable release.
- Italian translation (`it.json`) + language picker in Setup (English stays
  the source language; adding a language = one JSON file + PR).
- Complete in-HA documentation (DOCS.md): full field reference with practical
  examples — sprinkler precipitation-rate from catalog / catch-cup test,
  dripline calculator walkthrough, AI provider setup (OpenAI/Anthropic/HA
  conversation agent) step by step, MQTT exposure, FAQ, troubleshooting,
  privacy note.

## 0.9.0
- AI program generator (Milestone 9, optional): providers ha_conversation
  (your HA conversation agent, zero extra keys), anthropic or openai (API key
  in add-on options; optional ai_model override). The model receives config,
  zones, balance history, climate boundaries, the rule-based baseline and
  your free-text notes; must return strict JSON (validated, one retry, then
  automatic fallback to the rule-based proposal with a clear message).
- "Ask AI to review": plain-text suggestions comparing current programs with
  zones, climate and actual water-balance history.
- AI output is ALWAYS a proposal requiring your approval; AI never actuates
  valves.
- Programs tab: "Generate with AI" + notes field + review button (hidden
  when no provider is configured).

## 0.8.1
- Weather entity is now actually used (SPEC 6.1): its daily forecast
  precipitation overrides the Open-Meteo FORECAST rain in the daily
  calculation and rain-skip decisions (past actuals stay Open-Meteo).
  Unreadable entity -> logged warning + Open-Meteo fallback.
- "Test" button next to the weather entity field: shows the entity state and
  the next days' rain as the engine will see them
  (GET /api/weather/entity_test).
- README: one-click "Add repository to my Home Assistant" badge.

## 0.8.0
- HA entity exposure (Milestone 8, opt-in from Setup): per-zone deficit and
  next-run sensors, active zone/program sensors, plus a bidirectional system
  switch and watering-intensity number — all grouped under one "Hose
  Assistant" device.
- Primary path MQTT discovery (broker auto-detected via Supervisor services
  API, availability topic, retained states, commands from HA honored);
  fallback to REST read-only sensors when no broker is available.
- Refresh every 60 s; toggle takes effect within a minute.

## 0.7.0
- Operational controls (Milestone 7): System ON/OFF master toggle (OFF also
  stops any run in progress), rain delay 24/48/72h with cancel, per-run
  duration override from the dashboard.
- Safety: planned runs are re-checked at execution time — a system OFF or a
  rain delay set after planning skips them (with reason in the schedule).
- Endpoints: POST /api/system/on|off, /api/system/rain_delay?hours=,
  /api/schedule/{id}/override?minutes=.

## 0.6.0
- Rule-based program generator (Milestone 6): analyzes 5 years of local
  Open-Meteo climate, derives season boundaries from the ET0 curve (spring
  ≥2 mm/day, summer ≥4, etc. — not fixed dates) and proposes Lawn Start +
  Spring/Summer/Autumn (or a single season program in mild climates).
  Generate → preview with explanation → apply; re-applying replaces previous
  rules-generated programs, manual ones untouched.
- Programs tab: generate/preview/apply flow + program editor (dates, window,
  MAD, ET multiplier, priority, manual-only). Editing flips the badge to
  "manual".
- Endpoints: POST /api/programs/generate, POST /api/programs/apply.

## 0.5.1
- Richer irrigation types: fixed spray, rotor, MP rotator, micro-spray,
  surface drip, buried drip (soaker hose ≈ drip; tree bubblers ≈ high-flow
  drip; oscillating ≈ spray).
- Drip rate calculator in the zone editor: dripline length × emitter flow ÷
  spacing ÷ area → mm/h, one tap to apply.
- New "soil cover" per zone: bare / organic mulch / plastic film. Mulch
  lowers evaporation (Kc ×0.85 / ×0.75); plastic film also blocks most rain
  from the root zone (effective rain ×0.3).
- Automatic SQLite column migration for existing installs.

## 0.5.0
- Web UI (Milestone 5): mobile-first Preact + Tailwind SPA with bottom tab bar,
  dark/light theme, served at the panel root (dev page moved to /dev).
  - **Dashboard**: now/idle status, watering-intensity slider (applies live),
    per-zone soil-reservoir bars with dry threshold, upcoming runs with skip,
    run-zone / recalculate / STOP ALL controls, event log. Auto-refreshes.
  - **Zones**: card list + full editor (type/soil/vegetation presets that
    prefill rates, shade preset + fine slider, slope, max runtime).
  - **Setup**: location with auto elevation, master valve, thresholds; shown
    first on a fresh install.
  - **Programs**: read-only list (editor arrives with the generator).
- New endpoint: GET /api/status (dashboard payload).
- i18n scaffolding: English catalog; translations arrive in a later milestone.

## 0.4.1
- Dev page: zone management (list/add/delete) with valve-entity autocomplete
  from HA (input_boolean mocks first, then switches).

## 0.4.0
- Calculation engine (Milestone 4): per-zone water-balance deficit chain
  (ET0 x Kc_eff x intensity x program multiplier - effective rain - irrigation,
  clamped to [0, TAW]), MAD trigger, runtime from precipitation rate,
  cycle & soak for steep/low-infiltration zones, window packing with
  proportional reduction, seasonal program selection with priorities.
- Valve executor with hard failsafes: persisted watchdog turn-off on every
  valve open (survives restarts), close-all on startup, abort + close-all on
  HA API errors, strict one-zone-at-a-time sequencing, master valve support.
- APScheduler (SQLite job store in /data): daily calc at the configured time,
  automatic execution at the program window.
- New endpoints: GET /api/schedule, POST /api/schedule/{id}/skip,
  POST /api/run/zone/{id}?minutes=, POST /api/run/program/{id},
  POST /api/stop_all, POST /api/engine/recalc, GET /api/log.
- Dev page: recalc / run-zone / STOP ALL controls, schedule + log links.

## 0.3.0
- Weather + sun (Milestone 3): Open-Meteo client (daily FAO-56 ET0 +
  precipitation, past 7 days actuals + 7-day forecast), automatic elevation
  fetch when the location is set, sunrise/sunset via astral.
- New endpoints: `GET /api/weather/summary`, `GET /api/balance`,
  `POST /api/balance/refresh` (fills the per-zone water-balance table with
  et0, rain and effective crop coefficient; deficit comes with the engine).
- Crop coefficient model: monthly Kc tables (cool/warm season, shrubs) x
  shade factor (preset/fine slider/monthly curve).
- Temporary dev page: set location and trigger a balance refresh from the UI.

## 0.2.1
- Drop armv7 (32-bit) support: removed by Home Assistant and its builder in 2026.
  Supported architectures: aarch64, amd64.

## 0.2.0
- Data layer (Milestone 2): SQLite database persisted in `/data`, SQLAlchemy models
  for system config, zones, programs and the runtime tables.
- CRUD REST API: `GET/PUT /api/config`, `CRUD /api/zones`, `CRUD /api/programs`,
  with input validation and 404 handling.

## 0.1.0
- Initial skeleton: add-on boots, Ingress hello page, Supervisor API entity listing.
