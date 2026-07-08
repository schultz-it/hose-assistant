# Changelog

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
