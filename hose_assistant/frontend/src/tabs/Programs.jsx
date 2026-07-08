import { useEffect, useState } from "preact/hooks";
import { get } from "../api.js";
import { t } from "../i18n.js";
import { Card } from "../app.jsx";

// Read-only for now: creation/editing arrives with the program generator
// (Milestone 6). Programs created via API are listed here.
export function Programs() {
  const [programs, setPrograms] = useState(null);

  useEffect(() => {
    get("api/programs").then(setPrograms);
  }, []);

  if (!programs) return <p>{t("common.loading")}</p>;
  if (programs.length === 0)
    return <Card><p class="text-gray-500">{t("programs.empty")}</p></Card>;

  return (
    <div>
      {programs.map((p) => (
        <Card key={p.id}>
          <div class="flex items-center justify-between">
            <div>
              <div class="font-semibold" style={{ color: p.color }}>{p.name}</div>
              <div class="text-xs text-gray-500">
                {p.mode} · {p.date_start ?? "—"} → {p.date_end ?? "—"} ·{" "}
                {t("programs.window")} {p.window_start}–{p.window_end} ·{" "}
                {t("programs.mad")} {p.mad_pct}%
              </div>
            </div>
            <span class="text-xs rounded-full px-2 py-1 bg-gray-100 dark:bg-gray-800">
              {p.generated_by}
            </span>
          </div>
        </Card>
      ))}
    </div>
  );
}
