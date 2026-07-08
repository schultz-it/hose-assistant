import { useEffect, useState } from "preact/hooks";
import { get, put } from "../api.js";
import { t } from "../i18n.js";
import { Card, Field, inputCls, btnCls } from "../app.jsx";

export function Setup() {
  const [cfg, setCfg] = useState(null);
  const [entities, setEntities] = useState([]);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    get("api/config").then(setCfg);
    get("api/ha/entities?domain=switch")
      .then((r) => setEntities(r.entities.map((e) => e.entity_id)))
      .catch(() => {});
  }, []);

  if (!cfg) return <p>{t("common.loading")}</p>;

  const set = (k) => (e) => {
    const v = e.target.value;
    setCfg((prev) => ({ ...prev, [k]: v === "" ? null : v }));
  };

  async function save() {
    setMsg("…");
    try {
      const updated = await put("api/config", {
        latitude: cfg.latitude != null ? parseFloat(cfg.latitude) : null,
        longitude: cfg.longitude != null ? parseFloat(cfg.longitude) : null,
        units: cfg.units,
        master_valve_entity: cfg.master_valve_entity,
        master_valve_pre_open_s: parseInt(cfg.master_valve_pre_open_s || 5),
        daily_calc_time: cfg.daily_calc_time,
        forecast_rain_skip_mm: parseFloat(cfg.forecast_rain_skip_mm || 5),
        wind_skip_kmh: cfg.wind_skip_kmh != null ? parseFloat(cfg.wind_skip_kmh) : null,
        weather_entity: cfg.weather_entity,
      });
      setCfg(updated);
      setMsg(`${t("common.saved")} ✓`);
    } catch (e) {
      setMsg(`✗ ${e.message}`);
    }
  }

  return (
    <div>
      <Card title={t("setup.location")}>
        <div class="grid grid-cols-2 gap-3">
          <Field label={t("setup.latitude")}>
            <input class={inputCls} type="number" step="0.0001" value={cfg.latitude ?? ""}
              onInput={set("latitude")} />
          </Field>
          <Field label={t("setup.longitude")}>
            <input class={inputCls} type="number" step="0.0001" value={cfg.longitude ?? ""}
              onInput={set("longitude")} />
          </Field>
        </div>
        <p class="text-sm text-gray-500">
          {t("setup.elevation")}: {cfg.elevation_m ?? "—"} · {t("setup.timezone")}:{" "}
          {cfg.timezone ?? "auto"}
        </p>
      </Card>

      <Card title={t("setup.title")}>
        <Field label={t("setup.units")}>
          <select class={inputCls} value={cfg.units} onInput={set("units")}>
            <option value="metric">metric</option>
            <option value="imperial">imperial</option>
          </select>
        </Field>
        <Field label={t("setup.master_valve")}>
          <input class={inputCls} list="sw" value={cfg.master_valve_entity ?? ""}
            onInput={set("master_valve_entity")} placeholder="switch.pump" />
          <datalist id="sw">
            {entities.map((e) => <option key={e} value={e} />)}
          </datalist>
        </Field>
        <div class="grid grid-cols-2 gap-3">
          <Field label={t("setup.master_pre_open")}>
            <input class={inputCls} type="number" value={cfg.master_valve_pre_open_s}
              onInput={set("master_valve_pre_open_s")} />
          </Field>
          <Field label={t("setup.daily_calc")}>
            <input class={inputCls} type="time" value={cfg.daily_calc_time}
              onInput={set("daily_calc_time")} />
          </Field>
          <Field label={t("setup.rain_skip")}>
            <input class={inputCls} type="number" step="0.5" value={cfg.forecast_rain_skip_mm}
              onInput={set("forecast_rain_skip_mm")} />
          </Field>
          <Field label={t("setup.wind_skip")}>
            <input class={inputCls} type="number" value={cfg.wind_skip_kmh ?? ""}
              onInput={set("wind_skip_kmh")} />
          </Field>
        </div>
        <Field label={t("setup.weather_entity")}>
          <input class={inputCls} value={cfg.weather_entity ?? ""}
            onInput={set("weather_entity")} placeholder="weather.home" />
        </Field>
        <div class="flex items-center gap-3">
          <button class={btnCls} onClick={save}>{t("common.save")}</button>
          <span class="text-sm">{msg}</span>
        </div>
      </Card>
    </div>
  );
}
