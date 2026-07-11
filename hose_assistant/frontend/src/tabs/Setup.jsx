import { useEffect, useRef, useState } from "preact/hooks";
import { get, post, put } from "../api.js";
import { LANGUAGES, t } from "../i18n.js";
import { Card, Field, inputCls, btnCls, btnGray } from "../app.jsx";

export function Setup() {
  const [cfg, setCfg] = useState(null);
  const [entities, setEntities] = useState([]);
  const [msg, setMsg] = useState("");
  const [bkMsg, setBkMsg] = useState("");
  const fileRef = useRef(null);

  async function downloadBackup() {
    setBkMsg("…");
    try {
      const resp = await fetch("api/backup");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      const name = (resp.headers.get("Content-Disposition") || "")
        .match(/filename="(.+?)"/)?.[1] || "hose_assistant_backup.json";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = name; a.click();
      URL.revokeObjectURL(url);
      setBkMsg("✓");
    } catch (e) {
      setBkMsg(`✗ ${e.message}`);
    }
  }

  async function restoreBackup(file) {
    if (!file) return;
    if (!confirm(t("setup.restore_confirm"))) return;
    setBkMsg("…");
    try {
      const data = JSON.parse(await file.text());
      const res = await post("api/restore", data);
      setBkMsg(`✓ ${JSON.stringify(res.restored)}`);
      setTimeout(() => window.location.reload(), 800);
    } catch (e) {
      setBkMsg(`✗ ${e.message}`);
    }
  }

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
    const prevLang = (await get("api/config")).language || "en";
    try {
      const updated = await put("api/config", {
        language: cfg.language || "en",
        latitude: cfg.latitude != null ? parseFloat(cfg.latitude) : null,
        longitude: cfg.longitude != null ? parseFloat(cfg.longitude) : null,
        units: cfg.units,
        master_valve_entity: cfg.master_valve_entity,
        master_valve_pre_open_s: parseInt(cfg.master_valve_pre_open_s || 5),
        daily_calc_time: cfg.daily_calc_time,
        forecast_rain_skip_mm: parseFloat(cfg.forecast_rain_skip_mm || 5),
        wind_skip_kmh: cfg.wind_skip_kmh != null ? parseFloat(cfg.wind_skip_kmh) : null,
        weather_entity: cfg.weather_entity,
        rain_today_entity: cfg.rain_today_entity,
        expose_entities: !!cfg.expose_entities,
      });
      setCfg(updated);
      setMsg(`${t("common.saved")} ✓`);
      if ((updated.language || "en") !== prevLang) window.location.reload();
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
        <Field label={t("setup.language")}>
          <select class={inputCls} value={cfg.language || "en"} onInput={set("language")}>
            {Object.entries(LANGUAGES).map(([code, name]) => (
              <option key={code} value={code}>{name}</option>
            ))}
          </select>
        </Field>
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
          <div class="flex gap-2">
            <input class={inputCls} value={cfg.weather_entity ?? ""}
              onInput={set("weather_entity")} placeholder="weather.home" />
            <button class="rounded-lg bg-gray-200 dark:bg-gray-700 px-3 text-sm shrink-0"
              onClick={async () => {
                setMsg("…");
                try {
                  const r = await get("api/weather/entity_test");
                  const next = r.daily_rain_mm.slice(0, 3)
                    .map((d) => `${d.date.slice(5)}: ${d.rain_mm}mm`).join(" · ");
                  setMsg(`✓ ${r.entity} (${r.state}) — ${next}`);
                } catch (e) {
                  setMsg(`✗ ${e.message}`);
                }
              }}>
              {t("setup.weather_test")}
            </button>
          </div>
        </Field>
        <Field label={t("setup.rain_today_entity")}>
          <div class="flex gap-2">
            <input class={inputCls} value={cfg.rain_today_entity ?? ""}
              onInput={set("rain_today_entity")} placeholder="sensor.station_rain_today" />
            <button class="rounded-lg bg-gray-200 dark:bg-gray-700 px-3 text-sm shrink-0"
              onClick={async () => {
                setMsg("…");
                try {
                  const r = await get("api/weather/rain_sensor_test");
                  setMsg(`✓ ${r.entity} — ${r.rain_today_mm} mm`);
                } catch (e) {
                  setMsg(`✗ ${e.message}`);
                }
              }}>
              {t("setup.weather_test")}
            </button>
          </div>
          <p class="text-xs text-gray-400 mt-1">{t("setup.rain_today_hint")}</p>
        </Field>
        <label class="flex items-center gap-2 mb-3 text-sm">
          <input type="checkbox" checked={cfg.expose_entities}
            onChange={(e) => {
              const v = e.target.checked;
              setCfg((prev) => ({ ...prev, expose_entities: v }));
            }} />
          {t("setup.expose")}
        </label>
        <p class="text-xs text-gray-500 -mt-2 mb-3">{t("setup.expose_hint")}</p>
        <div class="flex items-center gap-3">
          <button class={btnCls} onClick={save}>{t("common.save")}</button>
          <span class="text-sm">{msg}</span>
        </div>
      </Card>

      <Card title={t("setup.backup")}>
        <p class="text-xs text-gray-500 mb-3">{t("setup.backup_hint")}</p>
        <div class="flex items-center gap-2 flex-wrap">
          <button class={btnGray} onClick={downloadBackup}>
            ⬇ {t("setup.backup_download")}
          </button>
          <button class={btnGray} onClick={() => fileRef.current?.click()}>
            ⬆ {t("setup.backup_restore")}
          </button>
          <input ref={fileRef} type="file" accept="application/json,.json"
            class="hidden"
            onChange={(e) => restoreBackup(e.target.files?.[0])} />
          <span class="text-sm">{bkMsg}</span>
        </div>
      </Card>
    </div>
  );
}
