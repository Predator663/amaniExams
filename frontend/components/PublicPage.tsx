"use client";
import Link from "next/link";
import { ReactNode } from "react";
import { useSession } from "@/lib/session";
import { SITE } from "@/lib/site";
import Footer from "./Footer";
import Logo from "./Logo";
import Shell from "./Shell";
import { Loading } from "./ui";

/** About and legal pages: open to everyone. Signed-in people keep their side menu; visitors get a simple header. */
export default function PublicPage({ title, updated, children }: { title: string; updated?: boolean; children: ReactNode }) {
  const { user, ready, t } = useSession();
  if (!ready) return <Loading />;
  const body = (
    <article className="doc">
      {updated && <p className="muted small">{t("last_updated")}: {SITE.updated}</p>}
      {children}
    </article>
  );
  if (user) return <Shell title={title}>{body}</Shell>;
  return (
    <div className="app focus public">
      <header className="top">
        <Link href="/login/" className="brand" aria-label={t("app_name")}><Logo size={38} /><span className="brand-name">{t("app_name")}</span></Link>
        <div className="top-right"><Link href="/login/" className="btn primary">{t("log_in")}</Link></div>
      </header>
      <main id="main" className="page" tabIndex={-1}><h1 className="page-title">{title}</h1>{body}</main>
      <Footer />
    </div>
  );
}
