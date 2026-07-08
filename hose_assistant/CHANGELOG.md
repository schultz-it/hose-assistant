# Changelog

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
