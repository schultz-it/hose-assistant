import { useEffect, useState } from "preact/hooks";
import { get, post, put, del } from "../api.js";
import { t } from "../i18n.js";
import { Card, Field, inputCls, btnCls, btnGray } from "../app.jsx";

function ProgramCard({ p, right }) {
  return (
    <Card>
      <div class="flex items-center justify-between gap-2">
        <div>
          <div class="font-semibold" style={{ color: p.color }}>{p.name}</div>
          <div class="text-xs text-gray-500">
            {p.mode === "fixed"
              ? (p.fixed_runs || []).map((r) => `${r.time}×${r.minutes_per_zone}'`).join(" ")
              : `${p.date_start ?? "—"} → ${p.date_end ?? "—"} · ${t("programs.window")} ${p.window_start}–${p.window_end} · ${t("programs.mad")} ${p.mad_pct}%`}
            {p.manual_only ? ` · ${t("programs.manual_only")}` : ""}
          </div>
          {p.ai_explanation && (
            <div class="text-xs text-gray-400 mt-1">{p.ai_explanation}</div>
          )}
        </div>
        <div class="flex gap-2 items-center shrink-0">
          <span class="text-xs rounded-full px-2 py-1 bg-gray-100 dark:bg-gray-800">
            {p.generated_by}
          </span>
          {right}
        </div>
      </div>
    </Card>
  );
}

function Editor({ program, onDone }) {
  const [p, setP] = useState({ ...program });
  const [msg, setMsg] = useState("");
  const set = (k) => (e) => {
    const v = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setP((prev) => ({ ...prev, [k]: v === "" ? null : v }));
  };
  async function save() {
    setMsg("…");
    try {
      const body = {
        ...p,
        mad_pct: parseFloat(p.mad_pct),
        et_multiplier: parseFloat(p.et_multiplier),
        priority: parseInt(p.priority || 0),
        generated_by: "manual", // edited by hand -> badge flips (SPEC 5.3)
      };
      await put(`api/programs/${p.id}`, body);
      onDone();
    } catch (e) {
      setMsg(`✗ ${e.message}`);
    }
  }
  return (
    <Card title={`${t("common.edit")}: ${p.name}`}>
      <div class="grid grid-cols-2 gap-3">
        <Field label={t("programs.name")}>
          <input class={inputCls} value={p.name} onInput={set("name")} />
        </Field>
        <Field label={t("programs.priority")}>
          <input class={inputCls} type="number" value={p.priority} onInput={set("priority")} />
        </Field>
        <Field label={t("programs.date_start")}>
          <input class={inputCls} value={p.date_start ?? ""} onInput={set("date_start")}
            placeholder="MM-DD" />
        </Field>
        <Field label={t("programs.date_end")}>
          <input class={inputCls} value={p.date_end ?? ""} onInput={set("date_end")}
            placeholder="MM-DD" />
        </Field>
        <Field label={t("programs.window_start")}>
          <input class={inputCls} type="time" value={p.window_start} onInput={set("window_start")} />
        </Field>
        <Field label={t("programs.window_end")}>
          <input class={inputCls} type="time" value={p.window_end} onInput={set("window_end")} />
        </Field>
        <Field label={`${t("programs.mad")} %`}>
          <input class={inputCls} type="number" value={p.mad_pct} onInput={set("mad_pct")} />
        </Field>
        <Field label={t("programs.et_mult")}>
          <input class={inputCls} type="number" step="0.05" value={p.et_multiplier}
            onInput={set("et_multiplier")} />
        </Field>
      </div>
      <label class="flex items-center gap-2 mb-3 text-sm">
        <input type="checkbox" checked={p.manual_only} onChange={set("manual_only")} />
        {t("programs.manual_only")}
      </label>
      <div class="flex gap-2 items-center">
        <button class={btnCls} onClick={save}>{t("common.save")}</button>
        <button class={btnGray} onClick={onDone}>{t("common.cancel")}</button>
        <span class="text-sm">{msg}</span>
      </div>
    </Card>
  );
}

export function Programs() {
  const [programs, setPrograms] = useState(null);
  const [proposal, setProposal] = useState(null); // {programs, explanation, climate}
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [ai, setAi] = useState({ available: false });
  const [notes, setNotes] = useState("");
  const [reviewText, setReviewText] = useState("");

  const load = () => get("api/programs").then(setPrograms);
  useEffect(() => {
    load();
    get("api/programs/ai_info").then(setAi).catch(() => {});
  }, []);

  async function generate(engine) {
    setBusy(true);
    setMsg(engine === "ai" ? t("programs.generating_ai") : t("programs.generating"));
    try {
      const out = await post("api/programs/generate", { engine, notes: notes || null });
      setProposal(out);
      setMsg(out.engine_used === "rules_fallback" ? `⚠ ${t("programs.ai_fallback")}` : "");
    } catch (e) {
      setMsg(`✗ ${e.message}`);
    }
    setBusy(false);
  }

  async function askReview() {
    setBusy(true);
    setMsg(t("programs.reviewing"));
    setReviewText("");
    try {
      const out = await post("api/programs/review", { notes: notes || null });
      setReviewText(out.review);
      setMsg("");
    } catch (e) {
      setMsg(`✗ ${e.message}`);
    }
    setBusy(false);
  }

  async function apply() {
    setBusy(true);
    try {
      await post("api/programs/apply", { programs: proposal.programs });
      setProposal(null);
      setMsg(`${t("common.saved")} ✓`);
      load();
    } catch (e) {
      setMsg(`✗ ${e.message}`);
    }
    setBusy(false);
  }

  if (!programs) return <p>{t("common.loading")}</p>;
  if (editing)
    return <Editor program={editing} onDone={() => { setEditing(null); load(); }} />;

  return (
    <div>
      {proposal ? (
        <div>
          <Card title={t("programs.proposal")}>
            <p class="text-sm text-gray-500 mb-2">{proposal.explanation}</p>
            <div class="flex gap-2 items-center">
              <button class={btnCls} disabled={busy} onClick={apply}>
                {t("programs.apply")}
              </button>
              <button class={btnGray} onClick={() => setProposal(null)}>
                {t("common.cancel")}
              </button>
            </div>
          </Card>
          {proposal.programs.map((p, i) => <ProgramCard key={i} p={p} />)}
        </div>
      ) : (
        <div>
          {programs.length === 0 && (
            <Card><p class="text-gray-500">{t("programs.empty")}</p></Card>
          )}
          {programs.map((p) => (
            <ProgramCard key={p.id} p={p} right={
              <>
                <button class={btnGray} onClick={() => setEditing(p)}>{t("common.edit")}</button>
                <button class="text-red-500 text-sm px-1"
                  onClick={() => del(`api/programs/${p.id}`).then(load)}>✕</button>
              </>
            } />
          ))}
          {ai.available && (
            <Card title={t("programs.ai_notes_title")}>
              <textarea class={`${inputCls} h-16`} value={notes}
                placeholder={t("programs.ai_notes_ph")}
                onInput={(e) => setNotes(e.target.value)} />
            </Card>
          )}
          {reviewText && (
            <Card title={t("programs.review_title")}>
              <p class="text-sm whitespace-pre-wrap">{reviewText}</p>
            </Card>
          )}
          <div class="flex gap-2 items-center flex-wrap">
            <button class={btnCls} disabled={busy} onClick={() => generate("rules")}>
              🪄 {t("programs.generate")}
            </button>
            {ai.available && (
              <button class="rounded-lg bg-violet-600 hover:bg-violet-700 text-white px-4 py-2 text-sm font-medium disabled:opacity-50"
                disabled={busy} onClick={() => generate("ai")}>
                ✨ {t("programs.generate_ai")}
              </button>
            )}
            {ai.available && programs.length > 0 && (
              <button class={btnGray} disabled={busy} onClick={askReview}>
                🔍 {t("programs.review_btn")}
              </button>
            )}
            <span class="text-sm">{msg}</span>
          </div>
        </div>
      )}
    </div>
  );
}
