import { useEffect, useState } from "preact/hooks";
import { setLang, t } from "./i18n.js";
import { get } from "./api.js";
import { Setup } from "./tabs/Setup.jsx";
import { Zones } from "./tabs/Zones.jsx";
import { Programs } from "./tabs/Programs.jsx";
import { Dashboard } from "./tabs/Dashboard.jsx";

const TABS = [
  { id: "dashboard", label: "tabs.dashboard", icon: "📊" },
  { id: "zones", label: "tabs.zones", icon: "💧" },
  { id: "programs", label: "tabs.programs", icon: "🗓️" },
  { id: "setup", label: "tabs.setup", icon: "⚙️" },
];

export function App() {
  // Default to Setup on first run (no location yet), Dashboard afterwards.
  const [tab, setTab] = useState(null);

  useEffect(() => {
    get("api/config")
      .then((c) => {
        setLang(c.language || "en");
        setTab(c.latitude == null ? "setup" : "dashboard");
      })
      .catch(() => setTab("setup"));
  }, []);

  if (tab === null)
    return <p class="p-8 text-center text-gray-500">{t("common.loading")}</p>;

  return (
    <div class="min-h-screen bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-100 pb-20">
      <header class="px-4 py-3 flex items-center gap-2 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 sticky top-0 z-10">
        <span class="text-2xl">🚿</span>
        <h1 class="text-lg font-semibold">Hose Assistant</h1>
      </header>

      <main class="max-w-xl mx-auto p-4">
        {tab === "dashboard" && <Dashboard />}
        {tab === "zones" && <Zones />}
        {tab === "programs" && <Programs />}
        {tab === "setup" && <Setup />}
      </main>

      <nav class="fixed bottom-0 inset-x-0 border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 flex">
        {TABS.map((x) => (
          <button
            key={x.id}
            onClick={() => setTab(x.id)}
            class={`flex-1 py-2 text-center text-xs ${
              tab === x.id
                ? "text-emerald-600 dark:text-emerald-400 font-semibold"
                : "text-gray-500"
            }`}
          >
            <div class="text-xl leading-6">{x.icon}</div>
            {t(x.label)}
          </button>
        ))}
      </nav>
    </div>
  );
}

export function Card({ title, children }) {
  return (
    <section class="mb-4 rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-4 shadow-sm">
      {title && <h2 class="font-semibold mb-3">{title}</h2>}
      {children}
    </section>
  );
}

export function Field({ label, children }) {
  return (
    <label class="block mb-3">
      <span class="block text-sm text-gray-500 dark:text-gray-400 mb-1">{label}</span>
      {children}
    </label>
  );
}

export const inputCls =
  "w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm";
export const btnCls =
  "rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 text-sm font-medium disabled:opacity-50";
export const btnGray =
  "rounded-lg bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 px-4 py-2 text-sm";
