# 🚿 Hose Assistant — Smart Irrigation for Home Assistant

> *Home Assistant runs your house. Hose Assistant runs your garden.*

Hose Assistant is a Home Assistant **add-on** that calculates, schedules and executes lawn/garden irrigation based on real evapotranspiration (FAO-56 ET₀ via Open-Meteo, no API key needed), weather forecasts, soil/grass/shade characteristics and seasonal programs — with a polished, mobile-first UI and optional AI-assisted program generation.

**Status: 🚧 under active development.** See [SPEC.md](SPEC.md) for the full specification and milestone plan.

## Installation

1. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
2. Add: `https://github.com/schultz-it/hose-assistant`
3. Install **Hose Assistant** and start it. Open the UI from the sidebar.

## Features (planned)

- Water-balance engine: ET₀ × crop coefficient × shade − rain, per zone
- Unlimited zones: spray/rotor/MP/drip, soil & grass types, slope with cycle & soak, monthly shade profiles
- 4 seasonal programs (Lawn Start, Spring, Summer, Autumn) — auto-generated from your local climate, or by AI
- Forecast rain skip, soil-moisture & rain-sensor skip, wind skip, rain delay, global intensity slider
- Hard hardware failsafes on every valve actuation
- Optional native HA entities via MQTT discovery
- English UI & docs, fully translatable (i18n)

## License

MIT
