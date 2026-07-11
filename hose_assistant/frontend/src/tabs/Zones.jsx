import { useEffect, useState } from "preact/hooks";
import { get, post, put, del } from "../api.js";
import { t } from "../i18n.js";
import { Card, Field, inputCls, btnCls, btnGray } from "../app.jsx";

// Default precipitation rate per irrigation type (SPEC 5.2).
const PR_DEFAULT = {
  spray: 35, rotor: 15, mp_rotator: 10, microspray: 20,
  drip: 6, subsurface_drip: 6,
};
const ROOT_DEFAULT = { cool_season: 15, warm_season: 20, shrubs_drip: 30 };
const SHADE_FINE = { full_sun: 0, partial: 40, shade: 80 };
const COVERS = ["none", "organic_mulch", "plastic_mulch"];
const isDrip = (t) => t === "drip" || t === "subsurface_drip";

const EMPTY = {
  name: "", valve_entity: "", irrigation_type: "spray",
  precipitation_rate_mmh: 35, emitter_lh: null, emitter_spacing_cm: null,
  line_length_m: null, cover: "none", soil_type: "loam",
  grass_type: "cool_season", root_depth_cm: 15, area_m2: null, slope: "flat",
  shade_preset: "full_sun", shade_fine: 0, max_runtime_min: 60,
  enabled: true, order: 0,
};

// Drip calculator: dripline length x emitter flow / spacing / wetted area.
function dripRate(z) {
  const { line_length_m: L, emitter_lh: q, emitter_spacing_cm: s, area_m2: A } = z;
  if (!L || !q || !s || !A) return null;
  const emitters = L / (s / 100);
  return Math.round((emitters * q / A) * 10) / 10; // mm/h == L/h per m2
}

export function Zones() {
  const [zones, setZones] = useState(null);
  const [reservoir, setReservoir] = useState({}); // zone_id -> {deficit_mm, taw_mm}
  const [editing, setEditing] = useState(null); // null | zone-like object
  const [entities, setEntities] = useState([]);
  const [msg, setMsg] = useState("");
  const [recalcMsg, setRecalcMsg] = useState("");
  const [recalcBusy, setRecalcBusy] = useState(false);

  const load = () => get("api/zones").then(setZones);
  const loadReservoir = () =>
    get("api/status").then((st) => {
      const map = {};
      for (const z of st.zones) map[z.id] = { deficit_mm: z.deficit_mm, taw_mm: z.taw_mm };
      setReservoir(map);
    }).catch(() => {});
  useEffect(() => {
    load();
    loadReservoir();
    Promise.all([
      get("api/ha/entities?domain=input_boolean").catch(() => ({ entities: [] })),
      get("api/ha/entities?domain=switch").catch(() => ({ entities: [] })),
      get("api/ha/entities?domain=valve").catch(() => ({ entities: [] })),
    ]).then((rs) => setEntities(rs.flatMap((r) => r.entities.map((e) => e.entity_id))));
  }, []);

  async function recalcNow() {
    setRecalcBusy(true);
    setRecalcMsg(t("zones.recalculating"));
    try {
      const r = await post("api/engine/recalc");
      setRecalcMsg(`✓ ${r.planned_runs} ${t("dash.planned_runs")}`);
      loadReservoir();
    } catch (e) {
      setRecalcMsg(`✗ ${e.message}`);
    }
    setRecalcBusy(false);
  }

  if (!zones) return <p>{t("common.loading")}</p>;

  // Functional update: rapid events (autofill, paste) must not clobber each other.
  const set = (k, cast = (x) => x) => (e) => {
    const v = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setEditing((prev) => {
      const next = { ...prev, [k]: v === "" ? null : cast(v) };
      // Presets: type prefills PR; grass prefills root depth; shade preset moves slider.
      if (k === "irrigation_type") next.precipitation_rate_mmh = PR_DEFAULT[v];
      if (k === "grass_type") next.root_depth_cm = ROOT_DEFAULT[v];
      if (k === "shade_preset") next.shade_fine = SHADE_FINE[v];
      return next;
    });
  };

  async function save() {
    setMsg("…");
    try {
      const numOrNull = (v) => (v != null && v !== "" ? parseFloat(v) : null);
      const body = {
        ...editing,
        precipitation_rate_mmh: parseFloat(editing.precipitation_rate_mmh),
        root_depth_cm: parseFloat(editing.root_depth_cm),
        area_m2: numOrNull(editing.area_m2),
        emitter_lh: numOrNull(editing.emitter_lh),
        emitter_spacing_cm: numOrNull(editing.emitter_spacing_cm),
        line_length_m: numOrNull(editing.line_length_m),
        shade_fine: parseInt(editing.shade_fine),
        max_runtime_min: parseInt(editing.max_runtime_min),
        order: parseInt(editing.order || 0),
      };
      if (editing.id) await put(`api/zones/${editing.id}`, body);
      else await post("api/zones", body);
      setEditing(null);
      setMsg("");
      load();
      loadReservoir(); // saving a zone auto-recalculates (SPEC) — reflect it
    } catch (e) {
      setMsg(`✗ ${e.message}`);
    }
  }

  async function remove(id) {
    await del(`api/zones/${id}`);
    load();
    loadReservoir();
  }

  if (editing)
    return (
      <Card title={editing.id ? `${t("common.edit")}: ${editing.name}` : t("common.add")}>
        <Field label={t("zones.name")}>
          <input class={inputCls} value={editing.name} onInput={set("name")} />
        </Field>
        <Field label={t("zones.valve")}>
          <input class={inputCls} list="ents" value={editing.valve_entity}
            onInput={set("valve_entity")} placeholder="switch.zone_1" />
          <datalist id="ents">{entities.map((e) => <option key={e} value={e} />)}</datalist>
        </Field>
        <div class="grid grid-cols-2 gap-3">
          <Field label={t("zones.type")}>
            <select class={inputCls} value={editing.irrigation_type} onInput={set("irrigation_type")}>
              {Object.keys(PR_DEFAULT).map((k) => (
                <option key={k} value={k}>{t(`zones.type.${k}`)}</option>
              ))}
            </select>
          </Field>
          <Field label={t("zones.pr")}>
            <input class={inputCls} type="number" step="0.5"
              value={editing.precipitation_rate_mmh} onInput={set("precipitation_rate_mmh")} />
          </Field>
          <Field label={t("zones.cover")}>
            <select class={inputCls} value={editing.cover} onInput={set("cover")}>
              {COVERS.map((k) => (
                <option key={k} value={k}>{t(`zones.cover.${k}`)}</option>
              ))}
            </select>
          </Field>
          <Field label={t("zones.soil")}>
            <select class={inputCls} value={editing.soil_type} onInput={set("soil_type")}>
              {["sandy", "loam", "clay"].map((k) => (
                <option key={k} value={k}>{t(`zones.soil.${k}`)}</option>
              ))}
            </select>
          </Field>
          <Field label={t("zones.grass")}>
            <select class={inputCls} value={editing.grass_type} onInput={set("grass_type")}>
              {Object.keys(ROOT_DEFAULT).map((k) => (
                <option key={k} value={k}>{t(`zones.grass.${k}`)}</option>
              ))}
            </select>
          </Field>
          <Field label={t("zones.root")}>
            <input class={inputCls} type="number" value={editing.root_depth_cm}
              onInput={set("root_depth_cm")} />
          </Field>
          <Field label={t("zones.area")}>
            <input class={inputCls} type="number" value={editing.area_m2 ?? ""}
              onInput={set("area_m2")} />
          </Field>
          <Field label={t("zones.slope")}>
            <select class={inputCls} value={editing.slope} onInput={set("slope")}>
              {["flat", "gentle", "steep"].map((k) => (
                <option key={k} value={k}>{t(`zones.slope.${k}`)}</option>
              ))}
            </select>
          </Field>
          <Field label={t("zones.max_runtime")}>
            <input class={inputCls} type="number" value={editing.max_runtime_min}
              onInput={set("max_runtime_min")} />
          </Field>
        </div>
        {isDrip(editing.irrigation_type) && (
          <div class="rounded-lg border border-dashed border-gray-300 dark:border-gray-700 p-3 mb-3">
            <div class="text-sm font-medium mb-2">{t("zones.drip_calc")}</div>
            <div class="grid grid-cols-3 gap-2">
              <Field label={t("zones.drip_line")}>
                <input class={inputCls} type="number" step="0.5"
                  value={editing.line_length_m ?? ""} onInput={set("line_length_m")} />
              </Field>
              <Field label={t("zones.drip_spacing")}>
                <input class={inputCls} type="number" step="1"
                  value={editing.emitter_spacing_cm ?? ""} onInput={set("emitter_spacing_cm")} />
              </Field>
              <Field label={t("zones.drip_flow")}>
                <input class={inputCls} type="number" step="0.1"
                  value={editing.emitter_lh ?? ""} onInput={set("emitter_lh")} />
              </Field>
            </div>
            {dripRate(editing) != null ? (
              <button
                class="text-sm text-emerald-600 dark:text-emerald-400 underline"
                onClick={() =>
                  setEditing((p) => ({ ...p, precipitation_rate_mmh: dripRate(p) }))
                }>
                {t("zones.drip_apply")} → {dripRate(editing)} mm/h
              </button>
            ) : (
              <span class="text-xs text-gray-500">{t("zones.drip_hint")}</span>
            )}
          </div>
        )}
        <Field label={t("zones.shade")}>
          <div class="flex gap-2 mb-2">
            {Object.keys(SHADE_FINE).map((k) => (
              <button key={k}
                class={`px-3 py-1 rounded-full text-sm border ${
                  editing.shade_preset === k
                    ? "bg-emerald-600 text-white border-emerald-600"
                    : "border-gray-300 dark:border-gray-700"
                }`}
                onClick={() => set("shade_preset")({ target: { value: k } })}>
                {t(`zones.shade.${k}`)}
              </button>
            ))}
          </div>
          <input type="range" min="0" max="100" class="w-full"
            value={editing.shade_fine} onInput={set("shade_fine")} />
          <span class="text-xs text-gray-500">
            {t("zones.shade_fine")}: ×{(1 - 0.005 * editing.shade_fine).toFixed(2)}
          </span>
        </Field>
        <label class="flex items-center gap-2 mb-3 text-sm">
          <input type="checkbox" checked={editing.enabled} onChange={set("enabled")} />
          {t("common.enabled")}
        </label>
        <div class="flex gap-2 items-center">
          <button class={btnCls} onClick={save}>{t("common.save")}</button>
          <button class={btnGray} onClick={() => setEditing(null)}>{t("common.cancel")}</button>
          <span class="text-sm">{msg}</span>
        </div>
      </Card>
    );

  return (
    <div>
      <div class="flex items-center gap-2 mb-3">
        <button class={btnGray} disabled={recalcBusy} onClick={recalcNow}>
          🔄 {t("zones.recalc_now")}
        </button>
        <span class="text-sm">{recalcMsg}</span>
      </div>
      {zones.length === 0 && (
        <Card><p class="text-gray-500">{t("zones.empty")}</p></Card>
      )}
      {zones.map((z) => {
        const r = reservoir[z.id];
        const left = r ? Math.max(0, r.taw_mm - r.deficit_mm) : null;
        return (
        <Card key={z.id}>
          <div class="flex items-center justify-between">
            <div>
              <div class="font-semibold">
                {z.name}
                {!z.enabled && <span class="ml-2 text-xs text-gray-400">(off)</span>}
              </div>
              <div class="text-xs text-gray-500">
                {z.valve_entity} · {t(`zones.type.${z.irrigation_type}`)} ·{" "}
                {z.precipitation_rate_mmh} mm/h · {t(`zones.soil.${z.soil_type}`)}
              </div>
              {r && (
                <div class="text-xs text-sky-600 dark:text-sky-400 mt-1">
                  💧 {t("zones.deficit_now")}: {left.toFixed(1)}/{r.taw_mm} mm
                </div>
              )}
            </div>
            <div class="flex gap-2">
              <button class={btnGray} onClick={() => setEditing({ ...z })}>
                {t("common.edit")}
              </button>
              <button class="text-red-500 text-sm px-2" onClick={() => remove(z.id)}>✕</button>
            </div>
          </div>
        </Card>
        );
      })}
      <button class={btnCls} onClick={() => setEditing({ ...EMPTY, order: zones.length })}>
        + {t("common.add")}
      </button>
    </div>
  );
}
