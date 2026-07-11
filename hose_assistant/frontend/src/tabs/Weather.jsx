import { useEffect, useState } from "preact/hooks";
import { get } from "../api.js";
import { getLocale, t } from "../i18n.js";
import { Card } from "../app.jsx";

const CONDITION_EMOJI = {
  "clear-night": "🌙", cloudy: "☁️", fog: "🌫️", hail: "🌨️",
  lightning: "⛈️", "lightning-rainy": "⛈️", partlycloudy: "⛅",
  pouring: "🌧️", rainy: "🌦️", snowy: "❄️", "snowy-rainy": "🌨️",
  sunny: "☀️", windy: "💨",
};
const CONDITION_KEY = {
  "clear-night": "weather.cond.clear_night", cloudy: "weather.cond.cloudy",
  fog: "weather.cond.fog", hail: "weather.cond.hail",
  lightning: "weather.cond.lightning", "lightning-rainy": "weather.cond.lightning_rainy",
  partlycloudy: "weather.cond.partlycloudy", pouring: "weather.cond.pouring",
  rainy: "weather.cond.rainy", snowy: "weather.cond.snowy",
  "snowy-rainy": "weather.cond.snowy_rainy", sunny: "weather.cond.sunny",
  windy: "weather.cond.windy",
};

// "YYYY-MM-DD" -> local calendar date, never shifted by UTC parsing.
function dayLabel(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return date.toLocaleDateString(getLocale(), { weekday: "short", day: "numeric", month: "short" });
}

const POLL_MS = 60000;

export function Weather() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  const refresh = () => {
    get("api/weather/now")
      .then((d) => { setData(d); setErr(""); })
      .catch((e) => setErr(e.message));
  };

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, []);

  if (err) {
    return (
      <Card title={t("weather.now")}>
        <p class="text-red-500 text-sm">✗ {err}</p>
      </Card>
    );
  }
  if (!data) return <p>{t("common.loading")}</p>;

  const { current, rain_skip, wind_skip, forecast, source, updated } = data;
  const emoji = CONDITION_EMOJI[current.condition] || "🌡️";
  const condLabel = current.condition ? t(CONDITION_KEY[current.condition] || current.condition) : "—";

  return (
    <div>
      <Card title={t("weather.now")}>
        <div class="flex items-center gap-3 mb-3">
          <span class="text-4xl leading-none">{emoji}</span>
          <div>
            <p class="text-lg font-semibold">{condLabel}</p>
            <p class="text-xs text-gray-500">
              {source === "ha_entity" ? t("weather.source_ha") : t("weather.source_openmeteo")}
            </p>
          </div>
        </div>
        <div class="grid grid-cols-3 gap-2 text-sm">
          <div>
            <span class="block text-gray-500 text-xs">{t("weather.temperature")}</span>
            {current.temperature_c != null ? `${current.temperature_c}°C` : "—"}
          </div>
          <div>
            <span class="block text-gray-500 text-xs">{t("weather.humidity")}</span>
            {current.humidity_pct != null ? `${current.humidity_pct}%` : "—"}
          </div>
          <div>
            <span class="block text-gray-500 text-xs">{t("weather.wind")}</span>
            {current.wind_kmh != null ? `${current.wind_kmh} km/h` : "—"}
          </div>
        </div>
        <p class="text-[11px] text-gray-400 mt-2">
          {t("weather.updated")}{" "}
          {new Date(updated).toLocaleTimeString(getLocale(), { hour: "2-digit", minute: "2-digit" })}
        </p>
      </Card>

      <Card title={t("weather.rain_skip")}>
        <div class={`rounded-lg p-3 text-sm font-semibold ${
          rain_skip.triggered
            ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
            : "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
        }`}>
          {rain_skip.triggered ? `⛔ ${t("weather.rain_skip_on")}` : `✅ ${t("weather.rain_skip_off")}`}
        </div>
        <p class="text-xs text-gray-500 mt-2">
          {t("weather.rain_skip_forecast_label")}: {rain_skip.rain_24h_mm} mm
          {" · "}
          {t("weather.rain_skip_threshold_label")}: {rain_skip.threshold_mm} mm
        </p>
      </Card>

      <Card title={t("weather.wind_skip")}>
        {!wind_skip.enabled ? (
          <p class="text-gray-500 text-sm">{t("weather.wind_skip_disabled")}</p>
        ) : (
          <>
            <div class={`rounded-lg p-3 text-sm font-semibold ${
              wind_skip.triggered
                ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                : "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
            }`}>
              {wind_skip.triggered ? `⛔ ${t("weather.wind_skip_on")}` : `✅ ${t("weather.wind_skip_off")}`}
            </div>
            <p class="text-xs text-gray-500 mt-2">
              {t("weather.wind_skip_max_label")}: {wind_skip.wind_max_kmh} km/h
              {" · "}
              {t("weather.rain_skip_threshold_label")}: {wind_skip.threshold_kmh} km/h
            </p>
          </>
        )}
        <p class="text-xs text-gray-400 mt-2">{t("weather.wind_skip_note")}</p>
      </Card>

      <Card title={t("weather.forecast")}>
        {forecast.length === 0 ? (
          <p class="text-gray-500 text-sm">{t("weather.no_data")}</p>
        ) : (
          <ul class="text-sm divide-y divide-gray-200 dark:divide-gray-800">
            {forecast.map((d) => (
              <li key={d.date} class="flex items-center justify-between py-1.5">
                <span class={d.is_forecast ? "" : "text-gray-400"}>{dayLabel(d.date)}</span>
                <span class="text-gray-500 text-xs">
                  🌧️ {d.rain_mm != null ? d.rain_mm.toFixed(1) : "—"} mm
                  {" · "}ET0 {d.et0 != null ? d.et0.toFixed(1) : "—"} mm
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
