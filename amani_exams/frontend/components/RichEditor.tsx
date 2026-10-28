"use client";
import { useEffect, useRef, useState } from "react";
import { api, API } from "@/lib/api";
import { Modal } from "./ui";

/** QB-05: bold, italic, underline, lists, superscript/subscript, special characters, formulas and chemical formulas, images. */
const SYMBOLS = "° ± × ÷ = ≠ ≈ ≤ ≥ < > π √ ∞ ∑ ∆ θ α β γ λ μ Ω ² ³ ½ ¼ ¾ → ← ⇌ ↑ ↓ ∠ ⊥ ∥ ∴ ∈ ∪ ∩ ‰ £ €".split(" ");

export async function uploadImage(file: File, alt: string): Promise<{ url: string; alt_text: string }> {
  const fd = new FormData();
  fd.append("image", file); fd.append("alt_text", alt);
  return api("/question-images/", { body: fd });
}

const toEditor = (html: string) => html.split('src="/media').join(`src="${API}/media`);
const fromEditor = (html: string) => html.split(`src="${API}/media`).join('src="/media');

function chem(src: string) {  // "H2O" -> H<sub>2</sub>O ; "SO4^2-" -> SO<sub>4</sub><sup>2-</sup>
  const [body, charge] = src.split("^");
  const h = body.replace(/([A-Za-z\)])(\d+)/g, "$1<sub>$2</sub>");
  return charge ? `${h}<sup>${charge}</sup>` : h;
}

function FormulaDialog({ onInsert, onClose }: { onInsert: (html: string) => void; onClose: () => void }) {
  const [kind, setKind] = useState<"frac" | "power" | "sub" | "root" | "chem">("frac");
  const [a, setA] = useState(""), [b, setB] = useState("");
  const html = kind === "frac" ? `<span class="formula" data-formula="${a}/${b}"><sup>${a || "a"}</sup>⁄<sub>${b || "b"}</sub></span>`
    : kind === "power" ? `${a || "x"}<sup>${b || "2"}</sup>` : kind === "sub" ? `${a || "x"}<sub>${b || "1"}</sub>`
    : kind === "root" ? `<span class="formula" data-formula="sqrt(${a})">√(${a || "x"})</span>` : `<span class="formula" data-formula="${a}">${chem(a || "H2O")}</span>`;
  const labels: Record<string, [string, string]> = { frac: ["Top", "Bottom"], power: ["Base", "Power"], sub: ["Base", "Subscript"], root: ["Inside the root", ""], chem: ["Formula, e.g. H2O or SO4^2-", ""] };
  return (
    <Modal label="Formula" onClose={onClose}>
      <h2>Formula</h2>
      <div className="chips" role="group" aria-label="Formula type">
        {([["frac", "Fraction"], ["power", "Power"], ["sub", "Subscript"], ["root", "Square root"], ["chem", "Chemical"]] as const).map(([k, l]) => (
          <button key={k} type="button" className={`chip ${kind === k ? "on" : ""}`} aria-pressed={kind === k} onClick={() => setKind(k)}>{l}</button>))}
      </div>
      <label className="field"><span>{labels[kind][0]}</span><input className="input" value={a} onChange={(e) => setA(e.target.value)} /></label>
      {labels[kind][1] && <label className="field"><span>{labels[kind][1]}</span><input className="input" value={b} onChange={(e) => setB(e.target.value)} /></label>}
      <p className="muted small">Preview</p>
      <div className="hint prompt" dangerouslySetInnerHTML={{ __html: html }} />
      <div className="row"><button type="button" className="btn" onClick={onClose}>Cancel</button><button type="button" className="btn primary" onClick={() => { onInsert(html); onClose(); }}>Insert</button></div>
    </Modal>
  );
}

function ImageDialog({ onInsert, onClose }: { onInsert: (html: string) => void; onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null), [alt, setAlt] = useState(""), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true); setErr("");
    try { const r = await uploadImage(file!, alt); onInsert(`<img src="${r.url}" alt="${alt.replace(/"/g, "&quot;")}">`); onClose(); }
    catch (e: any) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal label="Add image" onClose={onClose}>
      <h2>Add an image</h2>
      <label className="field"><span>Photo or picture (camera, gallery or computer)</span><input className="input" type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => setFile(e.target.files?.[0] || null)} /></label>
      <label className="field"><span>Short description for students who cannot see it (required)</span><input className="input" value={alt} onChange={(e) => setAlt(e.target.value)} maxLength={300} /></label>
      {err && <p className="no" role="alert">⚠ {err}</p>}
      <div className="row"><button type="button" className="btn" onClick={onClose}>Cancel</button><button type="button" className="btn primary" disabled={!file || !alt.trim() || busy} onClick={go}>{busy ? "Uploading…" : "Insert"}</button></div>
    </Modal>
  );
}

export default function RichEditor({ value, onChange, label, minRows = 4 }: { value: string; onChange: (html: string) => void; label: string; minRows?: number }) {
  const ref = useRef<HTMLDivElement>(null), saved = useRef<Range | null>(null), last = useRef<string>("");
  const [dlg, setDlg] = useState<"" | "formula" | "image" | "symbols">("");

  useEffect(() => { if (ref.current && value !== last.current) { ref.current.innerHTML = toEditor(value || ""); last.current = value || ""; } }, [value]);
  const emit = () => { const h = fromEditor(ref.current?.innerHTML || ""); last.current = h; onChange(h); };
  const remember = () => { const s = getSelection(); if (s && s.rangeCount && ref.current?.contains(s.anchorNode)) saved.current = s.getRangeAt(0).cloneRange(); };
  const restore = () => { ref.current?.focus(); const s = getSelection(); if (s && saved.current) { s.removeAllRanges(); s.addRange(saved.current); } };
  const cmd = (c: string) => { restore(); document.execCommand(c); emit(); };
  const insert = (html: string) => { restore(); document.execCommand("insertHTML", false, html); emit(); };
  const Btn = ({ c, children, title }: { c: string; children: React.ReactNode; title: string }) => (
    <button type="button" className="btn icon" title={title} aria-label={title} onMouseDown={(e) => { e.preventDefault(); remember(); }} onClick={() => cmd(c)}>{children}</button>);

  return (
    <div className="card" style={{ padding: ".6rem" }}>
      <div className="row" role="toolbar" aria-label={`${label} formatting`}>
        <Btn c="bold" title="Bold"><b>B</b></Btn><Btn c="italic" title="Italic"><i>I</i></Btn><Btn c="underline" title="Underline"><u>U</u></Btn>
        <Btn c="insertUnorderedList" title="Bulleted list">•≡</Btn><Btn c="insertOrderedList" title="Numbered list">1≡</Btn>
        <Btn c="superscript" title="Superscript">x²</Btn><Btn c="subscript" title="Subscript">x₂</Btn>
        <button type="button" className="btn" onMouseDown={(e) => { e.preventDefault(); remember(); }} onClick={() => setDlg("symbols")}>Ω Symbols</button>
        <button type="button" className="btn" onMouseDown={(e) => { e.preventDefault(); remember(); }} onClick={() => setDlg("formula")}>∑ Formula</button>
        <button type="button" className="btn" onMouseDown={(e) => { e.preventDefault(); remember(); }} onClick={() => setDlg("image")}>🖼 Image</button>
      </div>
      <div ref={ref} className="input rich" contentEditable suppressContentEditableWarning role="textbox" aria-multiline="true" aria-label={label}
        style={{ minHeight: `${minRows * 1.6}rem`, marginTop: ".5rem" }} onInput={emit} onBlur={() => { remember(); emit(); }}
        onPaste={(e) => { e.preventDefault(); document.execCommand("insertText", false, e.clipboardData.getData("text/plain")); }} />
      {dlg === "formula" && <FormulaDialog onInsert={insert} onClose={() => setDlg("")} />}
      {dlg === "image" && <ImageDialog onInsert={insert} onClose={() => setDlg("")} />}
      {dlg === "symbols" && (
        <Modal label="Symbols" onClose={() => setDlg("")}>
          <h2>Symbols</h2>
          <div className="chips">{SYMBOLS.map((s) => <button type="button" key={s} className="btn icon" aria-label={s} onClick={() => { insert(s); setDlg(""); }}>{s}</button>)}</div>
          <button type="button" className="btn" onClick={() => setDlg("")}>Close</button>
        </Modal>
      )}
    </div>
  );
}
