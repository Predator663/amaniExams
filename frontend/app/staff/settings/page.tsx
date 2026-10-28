"use client";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import StaffNav from "@/components/StaffNav";
import { ErrorNote, Loading, useLoad, Tabs } from "@/components/ui";
import { api } from "@/lib/api";
import { errorLines } from "@/lib/staff";
import { useSession } from "@/lib/session";

const THEMES = ["light", "dark", "high_contrast", "colour_blind", "soft"];
const NECTA = { grades: [
  { grade: "A", min: 75, max: 100, meaning: "Excellent", points: 1 }, { grade: "B", min: 65, max: 74, meaning: "Very good", points: 2 }, { grade: "C", min: 45, max: 64, meaning: "Good", points: 3 },
  { grade: "D", min: 30, max: 44, meaning: "Satisfactory (pass)", points: 4 }, { grade: "F", min: 0, max: 29, meaning: "Fail", points: 5 }],
  divisions: [{ division: "I", min: 7, max: 17, meaning: "Excellent" }, { division: "II", min: 18, max: 21, meaning: "Very good" }, { division: "III", min: 22, max: 25, meaning: "Good" },
    { division: "IV", min: 26, max: 33, meaning: "Pass" }, { division: "0", min: 34, max: 999, meaning: "Fail" }], subjects_counted: 7 };

function Msg({ errs, ok }: { errs: string[]; ok: string }) {
  return <>{errs.length > 0 && <div className="card error" role="alert">{errs.map((e, i) => <p key={i}>⚠ {e}</p>)}</div>}{ok && <p className="ok" role="status">✓ {ok}</p>}</>;
}

/** ADM-09: school name and logo, rules text, result delay, late entry, default theme and language, leaderboard, class position. */
function School() {
  const s = useLoad(() => api<any>("/settings/"));
  const [v, setV] = useState<any>(null), [errs, setErrs] = useState<string[]>([]), [ok, setOk] = useState("");
  useEffect(() => { if (s.data) setV(s.data); }, [s.data]);
  if (s.loading || !v) return <Loading />;
  if (s.error) return <ErrorNote error={s.error} retry={s.reload} />;
  const up = (p: any) => setV({ ...v, ...p });
  async function save() {
    setErrs([]); setOk("");
    try { const { logo_url, grade_scale, ...body } = v; const r = await api("/settings/", { method: "PATCH", body }); setV(r); setOk("Saved."); } catch (e: any) { setErrs(errorLines(e.data?.errors || e.data, e.message)); }
  }
  async function logo(f?: File) {
    if (!f) return; const fd = new FormData(); fd.append("logo", f);
    try { const r = await api<any>("/settings/logo/", { body: fd }); up({ logo_url: r.logo_url }); setOk("Logo saved."); } catch (e: any) { setErrs([e.message]); }
  }
  return (
    <div className="card">
      <label className="field"><span>School name</span><input className="input" value={v.school_name} onChange={(e) => up({ school_name: e.target.value })} /></label>
      <label className="field"><span>Logo {v.logo_url ? "(uploaded)" : ""}</span><input className="input" type="file" accept="image/*" onChange={(e) => logo(e.target.files?.[0])} /></label>
      <label className="field"><span>Default exam rules (shown when an exam has none of its own)</span><textarea className="input" rows={4} value={v.rules_text} onChange={(e) => up({ rules_text: e.target.value })} /></label>
      <div className="grid2">
        <label className="field"><span>Results appear this many minutes after the exam closes</span><input className="input" type="number" min={0} max={1440} value={v.result_delay_minutes} onChange={(e) => up({ result_delay_minutes: Number(e.target.value) })} /></label>
        <label className="field"><span>Late-entry window (minutes, no time added)</span><input className="input" type="number" min={0} max={180} value={v.late_entry_minutes} onChange={(e) => up({ late_entry_minutes: Number(e.target.value) })} /></label>
        <label className="field"><span>Default theme</span><select className="input" value={v.default_theme} onChange={(e) => up({ default_theme: e.target.value })}>{THEMES.map((t) => <option key={t}>{t}</option>)}</select></label>
        <label className="field"><span>Default language</span><select className="input" value={v.default_language} onChange={(e) => up({ default_language: e.target.value })}><option value="en">English</option><option value="sw">Kiswahili</option></select></label>
      </div>
      <label className="switch"><input type="checkbox" checked={v.leaderboard_enabled} onChange={(e) => up({ leaderboard_enabled: e.target.checked })} /> Class leaderboard (XP only)</label>
      <label className="switch"><input type="checkbox" checked={v.show_class_position} onChange={(e) => up({ show_class_position: e.target.checked })} /> Show class position on results</label>
      <Msg errs={errs} ok={ok} /><button className="btn primary" onClick={save}>Save settings</button>
    </div>
  );
}

/** RES-07, GRD-04: edit the NECTA scale. Published results keep the scale they were marked with. */
function Grading() {
  const s = useLoad(() => api<any>("/settings/"));
  const [sc, setSc] = useState<any>(null), [errs, setErrs] = useState<string[]>([]), [ok, setOk] = useState("");
  useEffect(() => { if (s.data) setSc(JSON.parse(JSON.stringify(s.data.grade_scale))); }, [s.data]);
  if (s.loading || !sc) return <Loading />;
  const setG = (i: number, p: any) => setSc({ ...sc, grades: sc.grades.map((g: any, j: number) => (j === i ? { ...g, ...p } : g)) });
  const setD = (i: number, p: any) => setSc({ ...sc, divisions: sc.divisions.map((g: any, j: number) => (j === i ? { ...g, ...p } : g)) });
  async function save() {
    setErrs([]); setOk("");
    try { await api("/settings/", { method: "PATCH", body: { grade_scale: sc } }); setOk("Saved. Old published results keep their old scale."); s.reload(); } catch (e: any) { setErrs(errorLines(e.data?.errors || e.data, e.message)); }
  }
  const n = (v: any, f: (x: number) => void, label: string) => <input className="input" style={{ width: 80 }} type="number" aria-label={label} value={v} onChange={(e) => f(Number(e.target.value))} />;
  return (
    <div className="card">
      <p className="hint">Defaults follow the NECTA O-Level scale. Please verify against official NECTA publications.</p>
      <h3>Subject grades</h3>
      <div className="tbl-wrap"><table><thead><tr><th>Grade</th><th>From %</th><th>To %</th><th>Meaning</th><th>Points</th></tr></thead><tbody>
        {sc.grades.map((g: any, i: number) => <tr key={i}><td><input className="input" style={{ width: 70 }} aria-label="Grade" value={g.grade} onChange={(e) => setG(i, { grade: e.target.value })} /></td><td>{n(g.min, (x) => setG(i, { min: x }), "From")}</td><td>{n(g.max, (x) => setG(i, { max: x }), "To")}</td>
          <td><input className="input" aria-label="Meaning" value={g.meaning} onChange={(e) => setG(i, { meaning: e.target.value })} /></td><td>{n(g.points, (x) => setG(i, { points: x }), "Points")}</td></tr>)}</tbody></table></div>
      <h3>Divisions (sum of the best subjects’ points, lower is better)</h3>
      <div className="tbl-wrap"><table><thead><tr><th>Division</th><th>From</th><th>To</th><th>Meaning</th></tr></thead><tbody>
        {sc.divisions.map((d: any, i: number) => <tr key={i}><td><input className="input" style={{ width: 70 }} aria-label="Division" value={d.division} onChange={(e) => setD(i, { division: e.target.value })} /></td><td>{n(d.min, (x) => setD(i, { min: x }), "From")}</td><td>{n(d.max, (x) => setD(i, { max: x }), "To")}</td><td><input className="input" aria-label="Meaning" value={d.meaning} onChange={(e) => setD(i, { meaning: e.target.value })} /></td></tr>)}</tbody></table></div>
      <label className="field"><span>Number of best subjects counted</span><input className="input" type="number" min={1} value={sc.subjects_counted} onChange={(e) => setSc({ ...sc, subjects_counted: Number(e.target.value) })} /></label>
      <Msg errs={errs} ok={ok} />
      <div className="row"><button className="btn primary" onClick={save}>Save scale</button><button className="btn" onClick={() => { if (confirm("Put the NECTA defaults back in the form? (not saved until you press Save)")) setSc(JSON.parse(JSON.stringify(NECTA))); }}>Use NECTA defaults</button></div>
    </div>
  );
}

/** SRS 5: XP values, levels, badge targets, streak freezes. */
function Gamification() {
  const g = useLoad(() => api<any>("/gamification/settings/"));
  const [v, setV] = useState<any>(null), [errs, setErrs] = useState<string[]>([]), [ok, setOk] = useState("");
  useEffect(() => { if (g.data) setV(JSON.parse(JSON.stringify({ xp_values: g.data.xp_values, levels: g.data.levels, badge_tiers: g.data.badge_tiers, freezes_per_month: g.data.freezes_per_month, practice_daily_xp_quizzes: g.data.practice_daily_xp_quizzes }))); }, [g.data]);
  if (g.loading || !v) return <Loading />;
  if (g.error) return <ErrorNote error={g.error} retry={g.reload} />;
  const def = g.data.defaults;
  async function save(body: any, msg: string) { setErrs([]); setOk(""); try { await api("/gamification/settings/", { method: "PATCH", body }); setOk(msg); g.reload(); } catch (e: any) { setErrs(errorLines(e.data?.errors || e.data, e.message)); } }
  const pretty = (k: string) => k.replace(/_/g, " ");
  return (
    <div className="card">
      <h3>XP values</h3>
      <div className="grid2">{Object.keys(def.xp_values).map((k) => <label key={k} className="field"><span>{pretty(k)} <span className="muted small">(default {def.xp_values[k]})</span></span><input className="input" type="number" min={0} max={1000} value={v.xp_values[k] ?? ""} onChange={(e) => setV({ ...v, xp_values: { ...v.xp_values, [k]: Number(e.target.value) } })} /></label>)}</div>
      <h3>Levels</h3>
      <div className="tbl-wrap"><table><thead><tr><th>#</th><th>Name</th><th>Kiswahili</th><th>XP needed</th></tr></thead><tbody>
        {v.levels.map((l: any, i: number) => <tr key={i}><td>{l.level}</td><td><input className="input" aria-label="Name" value={l.name} onChange={(e) => setV({ ...v, levels: v.levels.map((x: any, j: number) => (j === i ? { ...x, name: e.target.value } : x)) })} /></td>
          <td><input className="input" aria-label="Kiswahili name" value={l.name_sw} onChange={(e) => setV({ ...v, levels: v.levels.map((x: any, j: number) => (j === i ? { ...x, name_sw: e.target.value } : x)) })} /></td>
          <td><input className="input" style={{ width: 100 }} type="number" aria-label="XP" value={l.xp} onChange={(e) => setV({ ...v, levels: v.levels.map((x: any, j: number) => (j === i ? { ...x, xp: Number(e.target.value) } : x)) })} /></td></tr>)}</tbody></table></div>
      <h3>Badge targets (bronze, silver, gold)</h3>
      {Object.keys(def.badge_tiers).map((code) => <div key={code} className="row" style={{ margin: ".3rem 0" }}><span className="grow">{pretty(code)}</span>{[0, 1, 2].map((i) => <input key={i} className="input" style={{ width: 70 }} type="number" min={1} aria-label={`${code} ${["bronze", "silver", "gold"][i]}`} value={(v.badge_tiers[code] || def.badge_tiers[code])[i]} onChange={(e) => { const t = [...(v.badge_tiers[code] || def.badge_tiers[code])]; t[i] = Number(e.target.value); setV({ ...v, badge_tiers: { ...v.badge_tiers, [code]: t } }); }} />)}</div>)}
      <div className="grid2">
        <label className="field"><span>Streak freezes per month</span><input className="input" type="number" min={0} max={10} value={v.freezes_per_month} onChange={(e) => setV({ ...v, freezes_per_month: Number(e.target.value) })} /></label>
        <label className="field"><span>Practice quizzes per day that earn XP</span><input className="input" type="number" min={1} max={50} value={v.practice_daily_xp_quizzes} onChange={(e) => setV({ ...v, practice_daily_xp_quizzes: Number(e.target.value) })} /></label>
      </div>
      <Msg errs={errs} ok={ok} />
      <div className="row"><button className="btn primary" onClick={() => save(v, "Saved.")}>Save</button><button className="btn danger" onClick={() => confirm("Go back to the SRS defaults?") && save({ reset: true }, "Reset to the SRS defaults.")}>Reset to defaults</button></div>
    </div>
  );
}

/** ADM-04 and practice on/off per subject (SRS 5.5): classes, subjects, years and terms. */
function Setup() {
  const classes = useLoad(() => api<any[]>("/classes/")), subjects = useLoad(() => api<any[]>("/subjects/")), terms = useLoad(() => api<any[]>("/terms/")), years = useLoad(() => api<any[]>("/academic-years/"));
  const [c, setC] = useState({ name: "", form_level: 1, stream: "" }), [sub, setSub] = useState({ name: "", language: "en" }), [yr, setYr] = useState(""), [tm, setTm] = useState({ year: "", name: "", start_date: "", end_date: "" });
  const [errs, setErrs] = useState<string[]>([]);
  const run = async (fn: () => Promise<any>, after: () => void) => { setErrs([]); try { await fn(); after(); } catch (e: any) { setErrs(errorLines(e.data, e.message)); } };
  return (
    <>
      <Msg errs={errs} ok="" />
      <div className="card"><h3>Classes</h3>
        {classes.data?.map((x) => <div key={x.id} className="row"><span className="grow">{x.name} (Form {x.form_level}{x.stream ? `, stream ${x.stream}` : ""})</span><button className="btn danger" onClick={() => confirm(`Delete ${x.name}?`) && run(() => api(`/classes/${x.id}/`, { method: "DELETE" }), classes.reload)}>Delete</button></div>)}
        <div className="row" style={{ marginTop: ".6rem" }}><input className="input grow" placeholder="Name, e.g. Form 1A" aria-label="Class name" value={c.name} onChange={(e) => setC({ ...c, name: e.target.value })} />
          <select className="input" style={{ width: 100 }} aria-label="Form" value={c.form_level} onChange={(e) => setC({ ...c, form_level: Number(e.target.value) })}>{[1, 2, 3, 4].map((n) => <option key={n} value={n}>Form {n}</option>)}</select>
          <input className="input" style={{ width: 90 }} placeholder="Stream" aria-label="Stream" value={c.stream} onChange={(e) => setC({ ...c, stream: e.target.value })} />
          <button className="btn primary" disabled={!c.name} onClick={() => run(() => api("/classes/", { body: c }), () => { setC({ name: "", form_level: 1, stream: "" }); classes.reload(); })}>Add</button></div></div>
      <div className="card"><h3>Subjects and practice mode</h3>
        {subjects.data?.map((x) => <div key={x.id} className="row"><span className="grow">{x.name} <span className="muted small">({x.language === "sw" ? "Kiswahili" : "English"})</span></span>
          <label className="switch"><input type="checkbox" checked={x.practice_enabled} onChange={(e) => run(() => api(`/practice/subjects/${x.id}/toggle/`, { body: { enabled: e.target.checked } }), subjects.reload)} /> Practice</label></div>)}
        <div className="row" style={{ marginTop: ".6rem" }}><input className="input grow" placeholder="New subject" aria-label="Subject name" value={sub.name} onChange={(e) => setSub({ ...sub, name: e.target.value })} />
          <select className="input" style={{ width: 130 }} aria-label="Examined language" value={sub.language} onChange={(e) => setSub({ ...sub, language: e.target.value })}><option value="en">English</option><option value="sw">Kiswahili</option></select>
          <button className="btn primary" disabled={!sub.name} onClick={() => run(() => api("/subjects/", { body: sub }), () => { setSub({ name: "", language: "en" }); subjects.reload(); })}>Add</button></div></div>
      <div className="card"><h3>Academic years and terms</h3>
        {years.data?.map((y) => <p key={y.id} className="small">{y.name}{y.is_current ? " (current)" : ""}: {terms.data?.filter((t) => t.year === y.id).map((t) => t.name).join(", ") || "no terms"}</p>)}
        <div className="row"><input className="input grow" placeholder="Year, e.g. 2026" aria-label="Year" value={yr} onChange={(e) => setYr(e.target.value)} /><button className="btn" disabled={!yr} onClick={() => run(() => api("/academic-years/", { body: { name: yr, is_current: !years.data?.length } }), () => { setYr(""); years.reload(); })}>Add year</button></div>
        <div className="grid2" style={{ marginTop: ".6rem" }}>
          <select className="input" aria-label="Year for the term" value={tm.year} onChange={(e) => setTm({ ...tm, year: e.target.value })}><option value="">Year…</option>{years.data?.map((y) => <option key={y.id} value={y.id}>{y.name}</option>)}</select>
          <input className="input" placeholder="Term, e.g. Term 1" aria-label="Term name" value={tm.name} onChange={(e) => setTm({ ...tm, name: e.target.value })} />
          <label className="field"><span>Starts</span><input className="input" type="date" value={tm.start_date} onChange={(e) => setTm({ ...tm, start_date: e.target.value })} /></label>
          <label className="field"><span>Ends</span><input className="input" type="date" value={tm.end_date} onChange={(e) => setTm({ ...tm, end_date: e.target.value })} /></label>
        </div>
        <button className="btn" disabled={!tm.year || !tm.name || !tm.start_date || !tm.end_date} onClick={() => run(() => api("/terms/", { body: { ...tm, year: Number(tm.year) } }), () => { setTm({ year: "", name: "", start_date: "", end_date: "" }); terms.reload(); })}>Add term</button></div>
    </>
  );
}

export default function Settings() {
  const { user } = useSession();
  const [tab, setTab] = useState("school");
  const admin = user?.role === "admin" || user?.role === "super_admin";
  return (
    <Shell bare title="Settings">
      <StaffNav />
      {!admin ? <p>Only administrators can change settings.</p> : (
        <>
          <Tabs tabs={[["school", "School"], ["grading", "Grading scale"], ["gamification", "XP and badges"], ["setup", "Classes, subjects, terms"]]} value={tab} onChange={setTab} />
          {tab === "school" && <School />}{tab === "grading" && <Grading />}{tab === "gamification" && <Gamification />}{tab === "setup" && <Setup />}
        </>
      )}
    </Shell>
  );
}
