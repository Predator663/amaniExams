"use client";
import Link from "next/link";
import Logo from "@/components/Logo";
import PublicPage from "@/components/PublicPage";
import { useSession } from "@/lib/session";
import OperatorCard from "@/components/OperatorCard";
import { SITE } from "@/lib/site";

export default function About() {
  const { t } = useSession();
  return (
    <PublicPage title={t("about_title")}>
      <div className="about-hero"><Logo size={120} label="Amani Girls Secondary School crest" /><p className="lead">{SITE.app} is the online examination system of {SITE.school}. Girls sit their school exams on a phone, tablet or computer, the computer marks every answer, and results arrive on time and fairly.</p></div>

      <h2>What it does</h2>
      <div className="feat-grid">
        <div className="card"><h3>For students</h3><ul><li>Sit exams one question at a time, with a timer kept by the server</li><li>Answers save as you go and survive a lost connection</li><li>See results, review each answer with an explanation, and download a PDF slip</li><li>Practise, build a streak, earn XP and badges</li></ul></div>
        <div className="card"><h3>For teachers</h3><ul><li>Write six types of question, with images and formulas</li><li>Build papers by hand or from random rules</li><li>See topic heat maps and question analysis after results are published</li><li>Never mark by hand: marking is automatic</li></ul></div>
        <div className="card"><h3>For administrators</h3><ul><li>Bulk-create student accounts and print credential sheets</li><li>Schedule exams, watch the live monitor, grant extra time or retakes</li><li>Void a faulty question and every result recalculates</li><li>Full audit log of who did what</li></ul></div>
      </div>

      <h2>Built on four promises</h2>
      <ul>
        <li><b>Fair.</b> Everyone gets the same rules and the same clock. Nobody, including staff, can change an individual score.</li>
        <li><b>Private.</b> A student sees only her own results. Results stay hidden until the published time. <Link href="/privacy/">Read the privacy policy</Link>.</li>
        <li><b>Works on a phone.</b> It installs like an app, loads fast, and copes with weak signal.</li>
        <li><b>For everyone.</b> Five themes, larger text, a dyslexia-friendly font, read-aloud, and English or Kiswahili. <Link href="/accessibility/">Accessibility statement</Link>.</li>
      </ul>

      <h2>Install the app</h2>
      <p>Open the site in your phone’s browser, then choose “Add to Home screen” (or “Install”). Step-by-step help is on the <Link href="/install/">install page</Link> after you log in.</p>

      <h2 id="contact">Contact</h2>
      <div className="card">
        <p><b>{SITE.school}</b><br />{SITE.address}</p>
        <p>E-mail: <a href={`mailto:${SITE.email}`}>{SITE.email}</a><br />Phone: <a href={`tel:${SITE.phone.replace(/\s/g, "")}`}>{SITE.phone}</a></p>
        <p className="muted small">Forgotten password? Ask your teacher or the school administrator to reset it. Staff cannot see your password.</p>
      </div>

      <h2>Operator</h2>
      <OperatorCard />

      <h2>Version and credits</h2>
      <p>Version {SITE.version}, {SITE.year}. Developed for {SITE.school}{SITE.developer !== SITE.school ? ` by ${SITE.developer}` : ""}. Built with Django, Next.js and React.</p>
      <p><Link href="/terms/">Terms of use</Link> · <Link href="/privacy/">Privacy policy</Link> · <Link href="/accessibility/">Accessibility</Link></p>
    </PublicPage>
  );
}
