import { useEffect, useRef, useState } from "preact/hooks";
import { get, post, put } from "../api.js";
import { t } from "../i18n.js";
import { Card, inputCls, btnCls, btnGray } from "../app.jsx";

const POLL_MS = 5000;

export function Dashboard() {
  const [st, setSt] = useState(null);
  const [log, setLog] = useState([]);
  const [runZone, setRunZone] = useState({ id: "", minutes: 10 });
  const [msg, setMsg] = useState("");
  const timer = useRef(null);

  const refresh = () => {
    get("api/status").then(setSt).catch(() => {});
    get("api/log?limit=15").then(setLog).catch(() => {});
  };

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
          const pct = z.taw_mm ? Math.min(100, (z.deficit_mm / z.taw_mm) * 100) : 0;
          const dry = z.deficit_mm >= z.trigger_mm;
          return (
            <div key={z.id} class="mb-2">
              <div class="flex justify-between text-sm">
                <span>{z.name}</span>
                <span class={dry ? "text-amber-500" : "text-gray-500"}>
                  {z.deficit_mm}/{z.taw_mm} mm {dry ? `· ${t("dash.dry")}` : ""}
                </span>
              </div>
              <div class="h-2 rounded bg-gray-200 dark:bg-gray-800 overflow-hidden">
                <div class={`h-full ${dry ? "bg-amber-500" : "bg-emerald-500"}`}
                  style={{ width: `${pct}%` }} />
              </div>
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
              {zoneName(r.zone_id)} — {new Date(r.start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
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
            onClick={() => act(() => post("api/engine/recalc"))}>
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
