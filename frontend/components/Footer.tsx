"use client";
import Link from "next/link";
import { useSession } from "@/lib/session";
import Logo from "./Logo";
import { OPERATOR, SITE } from "@/lib/site";

export default function Footer({ compact }: { compact?: boolean }) {
  const { t } = useSession();
  const links = [["/about/", t("foot_about")], ["/privacy/", t("foot_privacy")], ["/terms/", t("foot_terms")], ["/accessibility/", t("foot_access")]];
  return (
    <footer className={`foot ${compact ? "compact" : ""}`}>
      <div className="foot-in">
        {!compact && (
          <div className="foot-brand"><Logo size={44} /><div><b>{SITE.app}</b><small>{SITE.school}</small></div></div>
        )}
        <nav className="foot-links" aria-label={t("foot_links")}>{links.map(([h, l]) => <Link key={h} href={h}>{l}</Link>)}</nav>
        <Link href="/about/#operator" className="foot-op">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={OPERATOR.avatar} alt="" width={28} height={28} aria-hidden loading="lazy" />
          <span>{OPERATOR.name} · <b>{OPERATOR.callsign.toUpperCase()}</b></span>
        </Link>
        <p className="foot-copy">© {SITE.year} {SITE.school}. {t("foot_rights")} · v{SITE.version}</p>
      </div>
    </footer>
  );
}
