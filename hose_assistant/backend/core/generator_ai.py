"""AI program generator (SPEC 7.2) — optional, proposal-only.

Providers (from add-on options, exported as env vars by the run script):
  * ``ha_conversation`` — the user's configured HA conversation agent via the
    Supervisor API (zero extra keys),
  * ``anthropic`` / ``openai`` — direct API with the user's key.

HARD RULE: the output is ALWAYS a proposal requiring explicit user approval
(the /apply endpoint is a user action). AI never actuates valves.

The model receives the full config/zones/balance bundle plus the rule-based
proposal as a grounded baseline, and must return strict JSON. Invalid output
is retried once with the validation error attached; if it still fails the
caller falls back to the rule-based proposal with a clear message.
"""
import json
import os
from datetime import date

import httpx
from sqlalchemy import select

from .. import models, schemas

TIMEOUT = 120.0
SUPERVISOR = "http://supervisor"

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5", "openai": "gpt-4o"}

SYSTEM_PROMPT = """You are an irrigation agronomist configuring seasonal watering programs
for a Home Assistant add-on that uses a FAO-56 water-balance model.

Return ONLY a JSON object, no prose before or after, with this shape:
{"programs": [<program>...], "explanation": "<short rationale for the user>"}

Each <program> object may use exactly these fields (defaults applied if omitted):
name, icon (mdi:*), color (#hex), mode ("budget"|"fixed"), date_start ("MM-DD"),
date_end ("MM-DD"), manual_only (bool), priority (int, higher wins on overlap),
allowed_days ({"weekdays":[0-6]} or {"every_n_days":N} or null),
window_start ("HH:MM"), window_end ("HH:MM"), mad_pct (0-100),
et_multiplier (>0), zone_overrides ({"<zone_id>":{"enabled":bool,"multiplier":float}}),
fixed_runs ([{"time":"HH:MM","minutes_per_zone":N}] — fixed mode only),
generated_by ("ai"), ai_explanation (string, per-program note).

Guidance: budget mode waters when zone deficit >= mad_pct% of its soil
reservoir; frequency emerges from zone physics. Water lawns pre-dawn in hot
months. Drip/mulched beds need lower MAD urgency and tolerate daytime windows.
Respect the local season boundaries provided. Set generated_by to "ai"."""


class AiError(Exception):
    pass


def provider_info() -> dict:
    provider = os.environ.get("AI_PROVIDER", "none")
    model = os.environ.get("AI_MODEL") or DEFAULT_MODELS.get(provider)
    available = provider == "ha_conversation" or (
        provider in ("anthropic", "openai") and bool(os.environ.get("AI_API_KEY")))
    return {"provider": provider, "model": model, "available": available}


def build_bundle(db, cfg, rules_out: dict, notes: str | None) -> str:
    """The user-context part of the prompt: config, zones, balance, baseline."""
    zones = db.scalars(select(models.Zone)).all()
    balance = db.scalars(
        select(models.WaterBalance).order_by(models.WaterBalance.date.desc()).limit(60)
    ).all()
    programs = db.scalars(select(models.Program)).all()
    bundle = {
        "today": date.today().isoformat(),
        "system": {
            "latitude": cfg.latitude, "longitude": cfg.longitude,
            "elevation_m": cfg.elevation_m, "watering_intensity": cfg.watering_intensity,
            "forecast_rain_skip_mm": cfg.forecast_rain_skip_mm,
            "wind_skip_kmh": cfg.wind_skip_kmh,
        },
        "zones": [
            {"id": z.id, "name": z.name, "type": z.irrigation_type,
             "pr_mmh": z.precipitation_rate_mmh, "soil": z.soil_type,
             "vegetation": z.grass_type, "root_cm": z.root_depth_cm,
             "cover": z.cover, "slope": z.slope, "shade_fine": z.shade_fine,
             "enabled": z.enabled}
            for z in zones
        ],
        "current_programs": [
            {"name": p.name, "mode": p.mode, "dates": [p.date_start, p.date_end],
             "window": [p.window_start, p.window_end], "mad_pct": p.mad_pct,
             "generated_by": p.generated_by}
            for p in programs
        ],
        "climate_season_boundaries": rules_out.get("climate"),
        "rule_based_baseline_proposal": rules_out.get("programs"),
        "recent_water_balance_sample": [
            {"zone_id": b.zone_id, "date": b.date, "et0": b.et0,
             "rain_mm": b.rain_mm, "irrigated_mm": b.irrigated_mm,
             "deficit_mm": b.deficit_mm}
            for b in balance[:30]
        ],
        "user_notes": notes or "",
    }
    return json.dumps(bundle, default=str)


# ------------------------------------------------------------- provider calls

async def _call_anthropic(prompt: str) -> str:
    info = provider_info()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": os.environ["AI_API_KEY"],
                     "anthropic-version": "2023-06-01"},
            json={"model": info["model"], "max_tokens": 4096,
                  "system": SYSTEM_PROMPT,
                  "messages": [{"role": "user", "content": prompt}]},
        )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


async def _call_openai(prompt: str) -> str:
    info = provider_info()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['AI_API_KEY']}"},
            json={"model": info["model"],
                  "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                               {"role": "user", "content": prompt}]},
        )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def _call_ha_conversation(prompt: str) -> str:
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{SUPERVISOR}/core/api/services/conversation/process?return_response",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": SYSTEM_PROMPT + "\n\n" + prompt},
        )
    resp.raise_for_status()
    body = resp.json()
    try:
        return body["service_response"]["response"]["speech"]["plain"]["speech"]
    except (KeyError, TypeError):
        raise AiError("Conversation agent returned an unexpected shape")


async def call_model(prompt: str) -> str:
    info = provider_info()
    if not info["available"]:
        raise AiError(f"AI provider not configured (provider={info['provider']})")
    fn = {"anthropic": _call_anthropic, "openai": _call_openai,
          "ha_conversation": _call_ha_conversation}[info["provider"]]
    return await fn(prompt)


# ------------------------------------------------------------- parse/validate

def parse_and_validate(text: str) -> dict:
    """Extract the JSON object and validate every program strictly."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise AiError("No JSON object in the model output")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise AiError(f"Invalid JSON: {exc}")
    raw = data.get("programs")
    if not isinstance(raw, list) or not raw:
        raise AiError("JSON lacks a non-empty 'programs' list")
    validated = []
    for i, p in enumerate(raw):
        try:
            model = schemas.ProgramCreate(**{**p, "generated_by": "ai"})
        except Exception as exc:  # pydantic ValidationError
            raise AiError(f"Program #{i + 1} invalid: {exc}")
        validated.append(model.model_dump())
    return {"programs": validated,
            "explanation": str(data.get("explanation") or "")}


async def generate(db, cfg, rules_out: dict, notes: str | None) -> dict:
    """Full AI generation with one retry on invalid output."""
    prompt = build_bundle(db, cfg, rules_out, notes)
    text = await call_model(prompt)
    try:
        out = parse_and_validate(text)
    except AiError as first_err:
        retry_prompt = (prompt + "\n\nYour previous answer was rejected: "
                        f"{first_err}. Return ONLY the corrected JSON object.")
        text = await call_model(retry_prompt)
        out = parse_and_validate(text)  # second failure propagates
    out["engine_used"] = "ai"
    return out


async def review(db, cfg, rules_out: dict, notes: str | None) -> str:
    """'Ask AI to review': plain-text suggestions on the current setup."""
    prompt = (build_bundle(db, cfg, rules_out, notes)
              + "\n\nInstead of JSON: review the current_programs against the "
                "zones, climate and recent water balance. Reply with short "
                "plain-text suggestions (max ~200 words) for the user.")
    return await call_model(prompt)
