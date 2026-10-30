import { OPERATOR } from "@/lib/site";

/** Operator card: avatar, name, call sign, e-mail, phone. Used on the About page; the look is strongest in the Modern Warfare III theme. */
export default function OperatorCard() {
  return (
    <section className="op-card" id="operator" aria-label="Operator">
      <div className="op-frame">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={OPERATOR.avatar} alt={OPERATOR.avatarAlt} width={120} height={120} loading="lazy" />
      </div>
      <div className="op-info">
        <span className="op-tag">Operator</span>
        <h3 className="op-name">{OPERATOR.name}</h3>
        <p className="op-call">Call sign <b>{OPERATOR.callsign.toUpperCase()}</b></p>
        <p className="op-links">
          <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>
          <a href={`tel:${OPERATOR.phoneTel}`}>{OPERATOR.phone}</a>
        </p>
      </div>
    </section>
  );
}
