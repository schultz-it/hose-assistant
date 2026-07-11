import { useEffect, useRef, useState } from "preact/hooks";
import { get, post, put } from "../api.js";
import { getLocale, t } from "../i18n.js";
import { Card, inputCls, btnCls, btnGray } from "../app.jsx";

const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

// "Tuesday 16 February · 04:00", localized, with today/tomorrow prefix.
function whenLabel(iso) {
  const d = new Date(iso);
  const loc = getLocale();
  const time = d.toLocaleTimeString(loc, { hour: "2-digit", minute: "2-digit" });
  const today = new Date();
  const tomorrow = new Date();
  tomorrow.setDate(today.getDate() + 1);
  const sameDay = (a, b) => a.toDateString() === b.toDateString();
  let day;
  if (sameDay(d, today)) day = t("dash.today");
  else if (sameDay(d, tomorrow)) day = t("dash.tomorrow");
  else day = cap(d.toLocaleDateString(loc, { weekday: "long", day: "numeric", month: "long" }));
  return `${day} · ${time}`;
}

const POLL_MS = 5000;

export function Dashboard() {
  const [st, setSt] = useState(null);
  const [log, setLog] = useState([]);
  const [history, setHistory] = useState({ irrigations: [], rain: [] });
  const [runZone, setRunZone] = useState({ id: "", minutes: 10 });
  const [msg, setMsg] = useState("");
  const [openDetail, setOpenDetail] = useState(null);
  const [detail, setDetail] = useState({});
  const timer = useRef(null);

  const refresh = () => {
    get("api/status").then(setSt).catch(() => {});
    get("api/log?limit=15").then(setLog).catch(() => {});
    get("api/history?limit=30").then(setHistory).catch(() => {});
  };

  async function toggleDetail(zoneId) {
    if (openDetail === zoneId) {
      setOpenDetail(null);
      return;
    }
    setOpenDetail(zoneId);
    try {
      const d = await get(`api/zones/${zoneId}/reservoir_detail`);
      setDetail((prev) => ({ ...prev, [zoneId]: d }));
    } catch (e) {
      setDetail((prev) => ({ ...prev, [zoneId]: null }));
    }
  }

  useEffect(() => {
    refresh();
    timer.current = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer.current);
  }, []);

  if (!st) return <p>{t("common.loading")}</p>;

  async function setIntensity(v) {
    setSt({ ...st, watering_intensity: v });
    try {
      await put("api/config", { watering_intensity: parseFloat(v) });
    } catch (e) {
      setMsg(`✗ ${e.message}`);
    }
  }

  async function act(fn) {
    setMsg("…");
    try {
      await fn();
      setMsg("✓");
      refresh();
    } catch (e) {
      setMsg(`✗ ${e.message}`);
    }
  }

  const zoneName = (id) => st.zones.find((z) => z.id === id)?.name ?? `#${id}`;

  return (
    <div>
      <Card title={t("dash.now")}>
        {!st.system_enabled ? (
          <p class="text-red-500 font-semibold">{t("dash.system_off")}</p>
        ) : st.busy ? (
          <p class="text-emerald-600 font-semibold animate-pulse">
            💦 {t("dash.running")}
          </p>
        ) : (
          <p class="text-gray-500">{t("dash.idle")}</p>
        )}
        {st.rain_delay_until && (
          <p class="text-sky-500 text-sm">
            🌧️ {t("dash.rain_delay")} {new Date(st.rain_delay_until).toLocaleString()}
          </p>
        )}
        <p class="text-sm text-gray-500 mt-1">
          {t("dash.active_program")}:{" "}
          {st.active_program ? st.active_program.name : t("dash.no_program")}
        </p>
      </Card>

      <Card title={`${t("dash.intensity")} — ×${st.watering_intensity.toFixed(2)}`}>
        <input type="range" min="0.5" max="2" step="0.05" class="w-full"
          value={st.watering_intensity}
          onChange={(e) => setIntensity(e.target.value)} />
        <div class="flex justify-between text-xs text-gray-500">
          <span>{t("dash.intensity.low")}</span>
          <span>{t("dash.intensity.normal")}</span>
          <span>{t("dash.intensity.extreme")}</span>
        </div>
      </Card>

      <Card title={t("dash.reservoir")}>
        {st.zones.map((z) => {
          // The bar shows WATER LEFT in the soil: full = fine, empty = dry.
          const left = Math.max(0, z.taw_mm - z.deficit_mm);
          const pct = z.taw_mm ? Math.min(100, (left / z.taw_mm) * 100) : 0;
          const dry = z.deficit_mm >= z.trigger_mm;
          return (
            <div key={z.id} class="mb-2">
              <div class="flex justify-between text-sm items-center">
                <span>{z.name}</span>
                <span class={`flex items-center gap-2 ${dry ? "text-amber-500" : "text-gray-500"}`}>
                  💧 {left.toFixed(1)}/{z.taw_mm} mm{dry ? ` · ${t("dash.dry")}` : ""}
                  <button class="w-4 h-4 leading-4 rounded-full border border-gray-300 dark:border-gray-700 text-gray-400 hover:text-sky-500 hover:border-sky-500 text-[10px]"
                    title={t("dash.reservoir_info")}
                    onClick={() => toggleDetail(z.id)}>
                    i
                  </button>
                  <button class="text-[10px] px-1 rounded border border-gray-300 dark:border-gray-700 text-gray-400 hover:text-sky-500 hover:border-sky-500"
                    title={t("dash.reset_reservoir")}
                    onClick={() => {
                      if (confirm(`${t("dash.reset_confirm")} — ${z.name}?`))
                        act(() => post(`api/zones/${z.id}/reset_reservoir?state=full`));
                    }}>
                    100%
                  </button>
                  <button class="text-[10px] px-1 rounded border border-gray-300 dark:border-gray-700 text-gray-400 hover:text-amber-500 hover:border-amber-500"
                    title={t("dash.reset_empty")}
                    onClick={() => {
                      if (confirm(`${t("dash.reset_empty_confirm")} — ${z.name}?`))
                        act(() => post(`api/zones/${z.id}/reset_reservoir?state=empty`));
                    }}>
                    0%
                  </button>
                </span>
              </div>
              <div class="h-2 rounded bg-gray-200 dark:bg-gray-800 overflow-hidden">
                <div class={`h-full ${dry ? "bg-amber-500" : "bg-sky-500"}`}
                  style={{ width: `${pct}%` }} />
              </div>
              {openDetail === z.id && (
                <div class="mt-1 mb-2 p-2 rounded bg-gray-100 dark:bg-gray-800 text-xs text-gray-600 dark:text-gray-300 space-y-0.5">
                  {!detail[z.id] ? (
                    <p>{t("common.loading")}</p>
                  ) : detail[z.id].date == null ? (
                    <p>{t("dash.detail_no_data")}</p>
                  ) : (
                    <>
                      <p>
                        {t("dash.detail_et")}: ET0 {detail[z.id].et0} mm × Kc {detail[z.id].kc_eff}
                        {" × "}{detail[z.id].watering_intensity} × {detail[z.id].et_multiplier}
                        {" ≈ "}{detail[z.id].et_loss_mm} mm
                      </p>
                      <p>
                        {t("dash.detail_rain")}: {detail[z.id].rain_mm} mm
                        {" ("}{t("dash.detail_rain_effective")}: {detail[z.id].effective_rain_mm} mm)
                      </p>
                      <p>{t("dash.detail_irrigated")}: {detail[z.id].irrigated_mm} mm</p>
                      <p>
                        {t("dash.detail_result")}:{" "}
                        {Math.max(0, detail[z.id].taw_mm - detail[z.id].deficit_mm).toFixed(1)}
                        /{detail[z.id].taw_mm} mm
                        {" — "}{t("dash.detail_date")} {detail[z.id].date}
                      </p>
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </Card>

      <Card title={t("dash.upcoming")}>
        {st.upcoming.length === 0 && (
          <p class="text-gray-500 text-sm">{t("dash.no_upcoming")}</p>
        )}
        {st.upcoming.map((r) => (
          <div key={r.id} class="flex items-center justify-between text-sm py-1">
            <span>
              {r.status === "running" ? "▶️ " : "🕐 "}
              {zoneName(r.zone_id)} — {r.status === "running" ? t("dash.running") : whenLabel(r.start)}
              {" · "}{Math.round(r.duration_min)} {t("common.minutes")}
            </span>
            {r.status === "planned" && (
              <span class="flex gap-2">
                <button class="text-xs text-gray-400 hover:text-emerald-500"
                  onClick={() => {
                    const m = prompt(t("dash.override_prompt"), Math.round(r.duration_min));
                    if (m) act(() => post(`api/schedule/${r.id}/override?minutes=${m}`));
                  }}>
                  ✎ {Math.round(r.duration_min)}'
                </button>
                <button class="text-xs text-gray-400 hover:text-red-500"
                  onClick={() => act(() => post(`api/schedule/${r.id}/skip`))}>
                  {t("dash.skip")}
                </button>
              </span>
            )}
          </div>
        ))}
      </Card>

      <Card title={t("dash.controls")}>
        <div class="flex gap-2 items-end flex-wrap">
          <label class="text-sm">
            <span class="block text-gray-500 mb-1">{t("dash.run_zone")}</span>
            <select class={inputCls} value={runZone.id}
              onInput={(e) => setRunZone({ ...runZone, id: e.target.value })}>
              <option value="">—</option>
              {st.zones.filter((z) => z.enabled).map((z) => (
                <option key={z.id} value={z.id}>{z.name}</option>
              ))}
            </select>
          </label>
          <label class="text-sm w-20">
            <span class="block text-gray-500 mb-1">{t("common.minutes")}</span>
            <input class={inputCls} type="number" min="1" max="240" value={runZone.minutes}
              onInput={(e) => setRunZone({ ...runZone, minutes: e.target.value })} />
          </label>
          <button class={btnCls} disabled={!runZone.id}
            onClick={() => act(() => post(`api/run/zone/${runZone.id}?minutes=${runZone.minutes}`))}>
            {t("dash.run")}
          </button>
          <button class={btnGray}
            onClick={async () => {
              setMsg("…");
              try {
                const r = await post("api/engine/recalc");
                setMsg(`✓ ${r.planned_runs} ${t("dash.planned_runs")}`);
                refresh();
              } catch (e) {
                setMsg(`✗ ${e.message}`);
              }
            }}>
            {t("dash.recalc")}
          </button>
          <button class="rounded-lg bg-red-600 hover:bg-red-700 text-white px-4 py-2 text-sm font-semibold"
            onClick={() => act(() => post("api/stop_all"))}>
            ⏹ {t("dash.stop_all")}
          </button>
          <span class="text-sm">{msg}</span>
        </div>
        <div class="flex gap-2 items-center flex-wrap mt-3 pt-3 border-t border-gray-200 dark:border-gray-800">
          <button
            class={`rounded-lg px-4 py-2 text-sm font-semibold ${
              st.system_enabled
                ? "bg-gray-200 dark:bg-gray-700"
                : "bg-emerald-600 text-white"
            }`}
            onClick={() =>
              act(() => post(st.system_enabled ? "api/system/off" : "api/system/on"))
            }>
            {st.system_enabled ? `⏻ ${t("dash.turn_off")}` : `⏻ ${t("dash.turn_on")}`}
          </button>
          <span class="text-sm text-gray-500">🌧️ {t("dash.rain_delay_btn")}:</span>
          {[24, 48, 72].map((h) => (
            <button key={h} class={btnGray}
              onClick={() => act(() => post(`api/system/rain_delay?hours=${h}`))}>
              {h}h
            </button>
          ))}
          {st.rain_delay_until && (
            <button class="text-xs text-red-500 underline"
              onClick={() => act(() => post("api/system/rain_delay?hours=0"))}>
              {t("dash.rain_delay_cancel")}
            </button>
          )}
        </div>
      </Card>

      <Card title={t("dash.history")}>
        <h3 class="text-xs font-semibold uppercase text-gray-400 mb-1">
          {t("dash.history_irrigations")}
        </h3>
        {history.irrigations.length === 0 && (
          <p class="text-gray-500 text-sm mb-2">{t("dash.history_empty")}</p>
        )}
        <ul class="text-sm space-y-1 mb-3">
          {history.irrigations.map((r) => (
            <li key={r.id} class="flex items-center justify-between">
              <span>
                {r.status === "done" ? "💧" : r.status === "aborted" ? "⚠️" : "⏭️"}{" "}
                {r.zone_name} — {whenLabel(r.start)}
              </span>
              <span class="text-gray-500 text-xs">
                {r.status === "done"
                  ? `${Math.round(r.duration_min)} ${t("common.minutes")}`
                  : r.status === "aborted"
                  ? t("dash.history_aborted")
                  : t("dash.history_skipped")}
              </span>
            </li>
          ))}
        </ul>
        <h3 class="text-xs font-semibold uppercase text-gray-400 mb-1">
          {t("dash.history_rain")}
        </h3>
        {history.rain.length === 0 && (
          <p class="text-gray-500 text-sm">{t("dash.history_no_rain")}</p>
        )}
        <ul class="text-sm space-y-1">
          {history.rain.map((r) => (
            <li key={r.date} class="flex items-center justify-between">
              <span>
                🌧️ {new Date(r.date).toLocaleDateString(getLocale(), { day: "numeric", month: "long" })}
              </span>
              <span class="text-gray-500 text-xs">{r.rain_mm} mm</span>
            </li>
          ))}
        </ul>
      </Card>

      <Card title={t("dash.log")}>
        <ul class="text-xs space-y-1 text-gray-600 dark:text-gray-300">
          {log.map((e, i) => (
            <li key={i}>
              <span class="text-gray-400">
                {new Date(e.ts).toLocaleString([], { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
              </span>{" "}
              {e.level === "error" ? "🔴" : e.level === "warning" ? "🟡" : "·"} {e.message}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
