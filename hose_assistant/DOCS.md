# Hose Assistant

Smart irrigation calculator & controller for Home Assistant: it computes how
much water every zone needs (FAO-56 water-balance model) **and** runs the
valves, with hard safety failsafes.

---

## 1. How the model works

Every zone has a *soil reservoir*. Each day the add-on updates a **deficit**
(how much water the root zone is missing, in mm):

```
deficit += ET0 × Kc_eff × intensity × program_multiplier
           − effective_rain − irrigation_applied
```

- **ET0** — reference evapotranspiration (mm/day) from Open-Meteo (free, no
  API key; only your coordinates are sent).
- **Kc_eff** = crop coefficient (per vegetation type and month) × shade
  factor × soil-cover factor.
- **effective_rain** = rain capped by the soil's infiltration capacity; under
  a plastic mulch film only ~30% reaches the roots.
- The deficit is clamped between 0 and **TAW** (total available water =
  soil AWC × root depth).

A zone is watered when its deficit reaches the program's **MAD** (Management
Allowed Depletion, % of TAW). Runtime = `deficit ÷ precipitation rate × 60`
minutes, capped at the zone's max runtime, split into **cycle & soak** when
the soil can't absorb fast enough (clay, steep slopes).

**Safety failsafes (always on):** every valve open schedules a persisted
watchdog turn-off at duration + 2 min (survives restarts); all valves are
closed on add-on start; any HA API error aborts the session and closes
everything; zones run strictly one at a time.

---

## 2. Setup tab — field reference

| Field | Meaning | Practical tip |
|---|---|---|
| Latitude / Longitude | Drives weather, sun and climate. | Use your garden's coordinates (right-click in Google Maps → copy). Elevation is fetched automatically, editable. |
| Units | Display only; everything is metric internally. | |
| Master valve / pump | A `switch.*` opened before any zone and closed after. | Leave empty if you don't have one. |
| Master pre-open (s) | Delay between master open and first zone. | 5 s is fine for most pumps. |
| Daily calculation time | When the engine recomputes the plan. | Default 03:00 — before dawn watering windows. |
| Skip if rain forecast ≥ mm/24h | Skips all runs if that much rain is coming. | 5 mm default. Lower it if your soil holds water well. |
| Skip spray zones if wind ≥ km/h | Wind blows spray away; drip is unaffected. | 20–30 km/h is a sensible threshold. Empty = disabled. |
| HA weather entity | Overrides the **forecast** rain with your own integration (past actuals stay Open-Meteo). | Press **Test** to see exactly what the engine will read. |
| Expose entities | Publishes sensors/switch/number back into HA (section 6). | |

---

## 3. Zones — field reference & examples

### Irrigation type and precipitation rate (PR)

The PR is **how many mm of water per hour** the zone applies over its area.
Defaults by type: fixed spray 35 · rotor 15 · MP rotator 10 · micro-spray 20
· drip 6 mm/h. Always prefer a real value:

**Example A — from the catalog (fixed sprays):** a Hunter/Rain Bird nozzle
datasheet states the precipitation rate directly (e.g. "10A nozzle: 39 mm/h
at 2.8 bar"). Fixed heads cover the whole area constantly → use the catalog
value as-is.

**Example B — rotors (moving jet):** catalog PR for rotors **already accounts
for the rotation** (that's why 15 vs 35 mm/h) — use the catalog matched-
precipitation value, don't divide it yourself.

**Example C — catch-cup test (any spray/rotor zone, most accurate):** place
4–6 straight-sided containers (e.g. tuna cans) around the zone, run it for
15 minutes, measure the average water depth in mm, multiply by 4 → mm/h.
12 mm average in 15 min → PR = 48 mm/h.

**Example D — dripline (use the built-in calculator):** 40 m of dripline,
emitters every 30 cm, 2 L/h each, over a 12 m² bed:
`(40 ÷ 0.30) emitters × 2 L/h ÷ 12 m² = 22.2 mm/h`. Enter line length,
spacing and emitter flow in the zone editor and tap **Use computed rate**.
Soaker hose ≈ drip with the equivalent flow; tree bubblers ≈ high-flow drip.

### Soil, vegetation, roots

| Soil | AWC | Infiltration | Notes |
|---|---|---|---|
| Sandy | 0.06 mm/mm | 25 mm/h | Small reservoir → frequent short watering. |
| Loam | 0.12 | 12 | The default. |
| Clay | 0.17 | 4 | Big reservoir but slow absorption → cycle & soak kicks in. |

Vegetation sets the monthly Kc curve and default root depth: cool-season
lawn (Kc peak 0.95, roots 15 cm), warm-season lawn (0.75, 20 cm),
shrubs/drip beds (0.50, 30 cm).

### Shade and soil cover

- **Shade**: full sun ×1.0 · partial ×0.8 · shade ×0.6, fine-tunable with the
  slider (factor 1.0→0.5). Advanced: a 12-value monthly curve via the API for
  shadows that change through the year.
- **Cover**: bare soil ×1.0 · organic mulch ×0.85 · plastic mulch film ×0.75
  on evaporation — **and the film also blocks ~70% of rainfall** from the
  roots, which the balance accounts for.

### Slope & max runtime

Steep slopes force cycle & soak (short bursts with pauses) to avoid runoff.
**Max runtime** is a hard per-session safety cap (default 60 min).

---

## 4. Programs

- **budget** mode (normal): waters a zone when deficit ≥ MAD% × TAW, within
  the time window, zones sequenced one at a time. Frequency emerges from the
  physics: drip beds and mulched zones dry out slower and water less often.
- **fixed** mode (Lawn Start): fixed short runs at fixed times (e.g.
  07:00/12:00/17:00 × 5 min) for seed germination. Keep it *manual only* and
  enable it only after seeding; disable after 4–6 weeks.

**Auto-generate from climate** analyzes ~5 years of local ET0 and derives the
season boundaries for YOUR location (spring starts when mean ET0 crosses
2 mm/day, summer 4 mm/day…), then proposes the programs. Review → Apply.
Re-generating replaces only generated programs; ones you edited by hand stay.

### AI generator (optional)

Set in the add-on **Configuration** tab (Settings → Add-ons → Hose Assistant
→ Configuration):

| Option | Value |
|---|---|
| `ai_provider` | `none` · `ha_conversation` · `anthropic` · `openai` |
| `ai_api_key` | required for anthropic/openai |
| `ai_model` | optional override (defaults: claude-sonnet-5 / gpt-4o) |

**Example — OpenAI:** create a key at <https://platform.openai.com/api-keys>
(“Create new secret key”, copy the `sk-…` string), then:

```yaml
ai_provider: openai
ai_api_key: sk-xxxxxxxxxxxxxxxx
ai_model: ""        # empty = default
```

Save → restart the add-on. The **Generate with AI** and **Ask AI to review**
buttons appear in the Programs tab.

**Example — Anthropic:** key from <https://console.anthropic.com/> →
`ai_provider: anthropic`, same steps.

**Example — zero keys:** if you already use a conversation agent in HA
(e.g. an LLM integration), set `ai_provider: ha_conversation` — the add-on
talks to it through Home Assistant, no extra key needed.

The AI receives your config, zones, water-balance history, local season
boundaries and your free-text notes ("lawn reseeded in September", "zone 3
pools water"). Its answer is strictly validated; if invalid it is retried
once, then the add-on **falls back to the rule-based proposal** with a clear
message. **AI output is always a proposal you must apply; AI never touches
the valves.**

---

## 5. Dashboard

- **Now** — running/idle status and the active program.
- **Watering intensity** — global 0.5×–2× multiplier applied live (holiday
  coming? drop it to 0.7; heatwave? raise it).
- **Soil reservoir** — per-zone deficit vs the dry threshold.
- **Upcoming runs** — skip (✕) or override the duration (✎) of any run.
- **Controls** — run a single zone, recalculate the plan, **STOP ALL**
  (panic button: closes everything immediately), System ON/OFF (OFF also
  stops the current run), rain delay 24/48/72 h.

---

## 6. Exposing entities to Home Assistant

Enable **Expose entities** in Setup. Within a minute you get, grouped under
one *Hose Assistant* device:

- `sensor.hose_assistant_zone_<id>_deficit` (mm) and `…_next_run` per zone,
- `sensor.hose_assistant_active_zone`, `sensor.hose_assistant_next_program`,
- `switch.hose_assistant_system_enabled` and
  `number.hose_assistant_intensity` — **bidirectional**: control them from
  dashboards/automations.

Best path: install the **Mosquitto broker** add-on + the MQTT integration →
full MQTT discovery. Without a broker a REST fallback publishes read-only
sensors (they disappear on HA restart until the next refresh — a documented
HA limitation).

**Automation example:** *notify me when the lawn is very dry and no rain is
coming*: trigger on `sensor.hose_assistant_zone_1_deficit` above 15.

---

## 7. Add-on options

| Option | Default | Meaning |
|---|---|---|
| `log_level` | `info` | `debug` for troubleshooting. |
| `ai_provider` / `ai_api_key` / `ai_model` | `none` | See section 4. |

---

## 8. FAQ & troubleshooting

**The panel shows "Location not configured".** Set latitude/longitude in
Setup first — everything depends on it.

**No runs are planned.** Check in order: system ON? rain delay off? a program
covering today (Programs tab)? zone deficits above the MAD threshold
(Dashboard bars — "dry")? rain forecast below your skip threshold (event
log tells you exactly why runs were skipped)?

**A valve stayed on / I panic.** Press **STOP ALL**. The persisted watchdog
would close it anyway at duration + 2 min, even after a crash or restart.

**Runs are shorter than expected.** The window may be too short for all
zones: the engine reduces runtimes proportionally and logs a warning —
widen the window or split programs.

**MQTT entities don't appear.** Install Mosquitto broker + MQTT integration,
then toggle Expose entities off/on. Check the add-on log.

**Testing safely.** Create `input_boolean` helpers and use them as valve
entities: full engine + executor behaviour, zero water. Swap in the real
`switch.*` entities only when you trust the schedule.

## 9. Privacy

Only your latitude/longitude are sent to Open-Meteo (weather, no account).
If — and only if — you invoke the AI features, your irrigation configuration
is sent to the provider you configured. Nothing else leaves your machine.
