# 🚿 Hose Assistant — Smart Irrigation for Home Assistant

> *Home Assistant runs your house. Hose Assistant runs your garden.*

Hose Assistant is a Home Assistant **add-on** that calculates, schedules and executes lawn/garden irrigation based on real evapotranspiration (FAO-56 ET₀ via Open-Meteo, no API key needed), weather forecasts, soil/grass/shade characteristics and seasonal programs — with a polished, mobile-first UI and optional AI-assisted program generation.

**Status: ✅ 1.0 released.** Full documentation ships inside the add-on (Documentation tab); the project specification lives in [SPEC.md](SPEC.md).

## Installation

[![Add repository to my Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fschultz-it%2Fhose-assistant)

Click the badge above, or manually:

1. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
2. Add: `https://github.com/schultz-it/hose-assistant`
3. Install **Hose Assistant** and start it. Open the UI from the sidebar.

## Features

- Water-balance engine: ET₀ × crop coefficient × shade − rain, per zone
- Unlimited zones: spray/rotor/MP/drip, soil & grass types, slope with cycle & soak, monthly shade profiles
- 4 seasonal programs (Lawn Start, Spring, Summer, Autumn) — auto-generated from your local climate, or by AI
- Forecast rain skip, soil-moisture & rain-sensor skip, wind skip, rain delay, global intensity slider
- Hard hardware failsafes on every valve actuation
- Optional native HA entities via MQTT discovery
- UI in 9 languages (EN, IT, FR, DE, ES, PT, ZH, JA, AR incl. right-to-left); docs in English; fully translatable (i18n)

## License

MIT
