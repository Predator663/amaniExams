"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { ExamCard } from "@/lib/types";
import A11yPanel from "./A11yPanel";
import Footer from "./Footer";
import Icon from "./Icon";
import Logo from "./Logo";
import { Dropdown, Loading, Modal } from "./ui";

/** HOME-04: during an exam window every page shows how many students are online (a number, never names, BR-08). */
function useOnline(enabled: boolean) {
  const [online, setOnline] = useState<number | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let live = false, stop = false, offset = 0;
    const check = async () => {
      try {
        const cards = await api<ExamCard[]>("/student/exams/");
        offset = cards[0] ? new Date(cards[0].server_time).getTime() - Date.now() : 0;
        live = cards.some((c) => { const n = Date.now() + offset; return new Date(c.start_at).getTime() <= n && n <= new Date(c.end_at).getTime(); });
        if (!live) setOnline(null);
      } catch { /* offline: keep the last state */ }
    };
    const beat = async () => {
      if (!live || stop) return;
      try { setOnline((await api<{ online: number }>("/presence/", { method: "POST", body: {} })).online); } catch { /* ignore */ }
    };
    check().then(beat);
    const a = setInterval(check, 60_000), b = setInterval(beat, 30_000);
    return () => { stop = true; clearInterval(a); clearInterval(b); };
  }, [enabled]);
  return online;
}

function useUnread(enabled: boolean) {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    const load = () => api<{ unread: number }>("/notifications/?unread=1").then((r) => setN(r.unread)).catch(() => {});
    load();
    const i = setInterval(load, 90_000);
    window.addEventListener("amani:notifications", load);
    return () => { clearInterval(i); window.removeEventListener("amani:notifications", load); };
  }, [enabled]);
  return n;
}

type Item = { href: string; icon: string; label: string };
type Group = { title?: string; items: Item[] };

export default function Shell({ children, bare, title }: { children: ReactNode; bare?: boolean; title?: string }) {
  const { user, ready, t, lang, logout, savePrefs } = useSession();
  const path = usePathname() || "/";
  const [panel, setPanel] = useState(false), [drawer, setDrawer] = useState(false);
  const isStudent = user?.role === "student";
  const admin = user?.role === "admin" || user?.role === "super_admin";
  const online = useOnline(isStudent);
  const unread = useUnread(!!user);
  const focus = !!bare && !path.startsWith("/staff");  // exam, first password, demo: no menus, nothing to distract
  const side = !!user && !focus;

  useEffect(() => {
    if (!ready) return;
    if (!user) location.replace("/login/");
    else if (user.must_change_password && !path.startsWith("/change-password")) location.replace("/change-password/");
  }, [ready, user, path]);
  useEffect(() => { setDrawer(false); }, [path]);
  useEffect(() => {
    if (!drawer) return;
    const prev = document.body.style.overflow; document.body.style.overflow = "hidden";
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setDrawer(false);
    document.addEventListener("keydown", esc);
    return () => { document.body.style.overflow = prev; document.removeEventListener("keydown", esc); };
  }, [drawer]);

  // Phones: tables with a header row turn into cards. Each cell gets its column name (see "table.stack" in globals.css).
  useEffect(() => {
    const main = document.getElementById("main");
    if (!main) return;
    let queued = false;
    const label = () => {
      queued = false;
      main.querySelectorAll<HTMLTableElement>(".tbl-wrap table").forEach((tb) => {
        const heads = Array.from(tb.querySelectorAll("thead th")).map((h) => (h.textContent || "").trim());
        if (!heads.length) return;
        tb.classList.add("stack");
        tb.querySelectorAll("tbody tr").forEach((tr) => Array.from(tr.children).forEach((td, i) => {
          if (td.getAttribute("data-label") !== (heads[i] || "")) td.setAttribute("data-label", heads[i] || "");
        }));
      });
    };
    const mo = new MutationObserver(() => { if (!queued) { queued = true; requestAnimationFrame(label); } });
    mo.observe(main, { childList: true, subtree: true });
    label();
    return () => mo.disconnect();
  }, [path, ready, user]);

  if (!ready || !user) return <Loading />;

  const student: Group[] = [
    { items: [
      { href: "/", icon: "home", label: t("nav_home") }, { href: "/results/", icon: "chart", label: t("nav_results") },
      { href: "/practice/", icon: "pencil", label: t("nav_practice") }, { href: "/badges/", icon: "medal", label: t("nav_badges") },
      { href: "/leaderboard/", icon: "trophy", label: t("leaderboard") }, { href: "/progress/", icon: "trend", label: t("my_analytics") } ] },
    { title: t("nav_more"), items: [
      { href: "/notifications/", icon: "bell", label: t("notifications") }, { href: "/settings/", icon: "sliders", label: t("nav_settings") },
      { href: "/install/", icon: "download", label: t("install_app") } ] },
  ];
  const staff: Group[] = [
    { title: "Teaching", items: [
      { href: "/staff/", icon: "home", label: "Overview" }, { href: "/staff/questions/", icon: "file", label: "Questions" }, { href: "/staff/exams/", icon: "calendar", label: "Exams" },
      { href: "/staff/monitor/", icon: "activity", label: "Live monitor" }, { href: "/staff/analytics/", icon: "chart", label: "Analytics" } ] },
    ...(admin ? [{ title: "Administration", items: [
      { href: "/staff/people/", icon: "users", label: "People" }, { href: "/staff/guardians/", icon: "phone", label: "Parents" }, { href: "/staff/school/", icon: "building", label: "School analytics" },
      { href: "/staff/audit/", icon: "shield", label: "Audit log" }, { href: "/staff/settings/", icon: "sliders", label: "Settings" } ] }] : []),
  ];
  const groups = isStudent ? student : staff;
  const active = (h: string) => (h === "/" ? path === "/" : h === "/staff/" ? path === "/staff/" || path === "/staff" : path.startsWith(h.replace(/\/$/, "")));
  const bottom = student[0].items.slice(0, 4).concat(student[1].items[1]);
  const name = `${user.first_name || ""} ${user.last_name || ""}`.trim() || user.username;
  const initials = (user.first_name || user.last_name ? `${(user.first_name || "")[0] || ""}${(user.last_name || "")[0] || ""}` : user.username.slice(0, 2)).toUpperCase();
  const role = user.role === "student" ? t("role_student") : user.role === "teacher" ? "Teacher" : user.role === "super_admin" ? "Super admin" : "Admin";

  return (
    <div className={`app ${side ? "with-side" : "focus"} ${isStudent && side ? "is-student" : ""}`}>
      <a href="#main" className="skip">{t("skip_to_content")}</a>
      {side && (
        <>
          <aside className={`side ${drawer ? "open" : ""}`} aria-label={t("main_menu")}>
            <div className="side-head">
              <Link href={isStudent ? "/" : "/staff/"} className="brand" aria-label={t("app_name")}><Logo size={38} /><span className="brand-name">{t("app_name")}</span></Link>
              <button type="button" className="side-close" onClick={() => setDrawer(false)} aria-label={t("close")}><Icon n="x" /></button>
            </div>
            <nav className="side-nav">
              {groups.map((g, gi) => (
                <div key={gi} className="side-group">
                  {g.title && <div className="side-title">{g.title}</div>}
                  {g.items.map((n) => (
                    <Link key={n.href} href={n.href} className={`side-link ${active(n.href) ? "on" : ""}`} aria-current={active(n.href) ? "page" : undefined}>
                      <Icon n={n.icon} /><span>{n.label}</span>
                      {n.href === "/notifications/" && unread > 0 && <b className="side-count">{unread > 9 ? "9+" : unread}</b>}
                    </Link>
                  ))}
                </div>
              ))}
            </nav>
            <div className="side-foot"><span className="avatar">{initials}</span><span className="who"><b>{name}</b><small>{role}</small></span></div>
          </aside>
          {drawer && <div className="scrim" onClick={() => setDrawer(false)} aria-hidden />}
        </>
      )}
      <div className="main-col">
        <header className="top">
          {side && <button type="button" className="btn icon menu-btn" onClick={() => setDrawer(true)} aria-label={t("open_menu")} aria-expanded={drawer}><Icon n="menu" /></button>}
          <Link href="/" className={`brand ${side ? "top-brand" : ""}`} aria-label={t("app_name")}><Logo size={38} /><span className="brand-name">{t("app_name")}</span></Link>
          <div className="top-right">
            {online !== null && <span className="pill live" role="status" aria-label={t("online_n", { n: online })}>● {t("online_n", { n: online })}</span>}
            <button type="button" className="btn icon ghost" onClick={() => setPanel(true)} aria-label={t("accessibility")} title={t("accessibility")}><Icon n="access" /></button>
            <Link href="/notifications/" className="btn icon ghost bell" aria-label={`${t("notifications")}${unread ? `: ${unread}` : ""}`}><Icon n="bell" />{unread > 0 && <b className="badge-dot">{unread > 9 ? "9+" : unread}</b>}</Link>
            {side && (
              <Dropdown label={name} button={<><span className="avatar sm">{initials}</span><span className="dd-name">{name}</span><Icon n="chevron" size={16} /></>}>
                <div className="dd-head"><b>{name}</b><small>{role}</small></div>
                {(isStudent || admin) && <Link role="menuitem" className="dd-item" href={isStudent ? "/settings/" : "/staff/settings/"}><Icon n="sliders" />{t("nav_settings")}</Link>}
                <Link role="menuitem" className="dd-item" href="/change-password/"><Icon n="key" />{t("change_password")}</Link>
                <button role="menuitem" type="button" className="dd-item" onClick={() => setPanel(true)}><Icon n="access" />{t("accessibility")}</button>
                <div className="dd-sep" role="separator" />
                <div className="dd-label"><Icon n="globe" size={14} />{t("language_menu")}</div>
                {([["en", "English"], ["sw", "Kiswahili"]] as const).map(([l, label]) => (
                  <button key={l} role="menuitemradio" aria-checked={lang === l} type="button" className="dd-item sub" onClick={() => savePrefs({ language: l })}>{label}{lang === l && <Icon n="check" size={16} />}</button>
                ))}
                <div className="dd-sep" role="separator" />
                <button role="menuitem" type="button" className="dd-item danger" onClick={() => logout()}><Icon n="logout" />{t("log_out")}</button>
              </Dropdown>
            )}
          </div>
        </header>
        <main id="main" className="page" tabIndex={-1}>
          {title && <h1 className="page-title">{title}</h1>}
          {children}
        </main>
        {!focus && <Footer />}
      </div>
      {isStudent && side && (
        <nav className="bottom" aria-label={t("main_menu")}>
          {bottom.map((n) => (
            <Link key={n.href} href={n.href} className={active(n.href) ? "on" : ""} aria-current={active(n.href) ? "page" : undefined}>
              <Icon n={n.icon} size={22} /><small>{n.label}</small>
            </Link>
          ))}
        </nav>
      )}
      {panel && (
        <Modal label={t("accessibility")} onClose={() => setPanel(false)}>
          <h2>{t("accessibility")}</h2>
          <A11yPanel compact />
          <button className="btn primary" onClick={() => setPanel(false)}>{t("done")}</button>
        </Modal>
      )}
    </div>
  );
}
