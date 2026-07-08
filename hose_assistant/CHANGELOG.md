# Changelog

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
