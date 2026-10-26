"use client";
import Shell from "@/components/Shell";
import StaffNav from "@/components/StaffNav";
import { Bar, ErrorNote, Loading, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

function Group({ title, rows }: { title: string; rows: any[] }) {
  if (!rows?.length) return null;
  return (
    <div className="card"><h3>{title}</h3>
      {rows.map((r) => <div key={String(r.key) + r.label} style={{ margin: ".6rem 0" }}><div className="row"><span className="grow">{r.label}</span><span className="muted small">{r.count} result(s) · pass {r.pass_rate ?? "–"}%</span><b>{r.average ?? "–"}%</b></div><Bar value={r.average || 0} label={`${title}: ${r.label}`} /></div>)}
    </div>
  );
}

/** ADM-08: results by subject, class, stream and term; participation; engagement (numbers only, no marks). */
export default function SchoolAnalytics() {
  const { user } = useSession();
  const admin = user?.role === "admin" || user?.role === "super_admin";
  const a = useLoad(() => (admin ? api<any>("/analytics/school/") : Promise.resolve(null)), [admin]);
  const d = a.data, e = d?.engagement;
  return (
    <Shell bare title="School analytics">
      <StaffNav />
      {!admin ? <p>Only administrators can see school-wide analytics.</p> : a.loading ? <Loading /> : a.error || !d ? <ErrorNote error={a.error} retry={a.reload} /> : (
        <>
          {d.count === 0 ? <div className="card"><p className="muted">No published results yet.</p></div> : (
            <>
              <div className="grid3"><div className="stat"><b>{d.count}</b>Results</div><div className="stat"><b>{d.average}%</b>Average</div><div className="stat"><b>{d.pass_rate}%</b>Pass rate</div>
                <div className="stat"><b>{d.highest}%</b>Highest</div><div className="stat"><b>{d.lowest}%</b>Lowest</div><div className="stat"><b>{d.participation.overall_rate ?? "–"}%</b>Participation</div></div>
              <div className="card"><h3>Grade distribution</h3><p>{Object.entries(d.grade_distribution).map(([g, n]) => `${g}: ${n}`).join("   ")}</p></div>
              <Group title="By subject" rows={d.by_subject} /><Group title="By class" rows={d.by_class} /><Group title="By stream" rows={d.by_stream} /><Group title="By term" rows={d.by_term} />
              <div className="card"><h3>Participation by exam</h3><div className="tbl-wrap"><table><thead><tr><th>Exam</th><th>Took it</th><th>Eligible</th><th>Rate</th></tr></thead><tbody>
                {d.participation.exams.map((x: any) => <tr key={x.exam_id}><td>{x.title}</td><td>{x.participants}</td><td>{x.eligible}</td><td>{x.rate ?? "–"}%</td></tr>)}</tbody></table></div></div>
            </>
          )}
          {e?.available && (
            <div className="card"><h3>Engagement</h3>
              <div className="grid3"><div className="stat"><b>{e.active_rate_last_7_days ?? "–"}%</b>Active in 7 days</div><div className="stat"><b>{e.average_current_streak}</b>Avg streak</div><div className="stat"><b>{e.students_with_7_day_streak}</b>7-day streaks</div>
                <div className="stat"><b>{e.total_xp}</b>Total XP</div><div className="stat"><b>{e.practice_sessions_last_30_days}</b>Practice (30 days)</div><div className="stat"><b>{e.students}</b>Students</div></div>
              <div className="tbl-wrap"><table><thead><tr><th>Class</th><th>Students</th><th>Avg XP</th><th>Avg streak</th><th>Active (7 days)</th></tr></thead><tbody>
                {e.by_class.map((c: any) => <tr key={c.class}><td>{c.class}</td><td>{c.students}</td><td>{c.average_xp}</td><td>{c.average_current_streak}</td><td>{c.active_last_7_days}</td></tr>)}</tbody></table></div>
              {e.practice_by_subject.length > 0 && <p className="muted small">Practice sessions: {e.practice_by_subject.map((p: any) => `${p.subject} ${p.sessions}`).join(" · ")}</p>}
            </div>
          )}
        </>
      )}
    </Shell>
  );
}
