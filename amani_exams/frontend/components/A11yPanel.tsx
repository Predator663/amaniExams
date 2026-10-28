"use client";
import { useSession } from "@/lib/session";
import { speechSupported } from "@/lib/speech";

export const THEME_LIST = ["light", "dark", "high_contrast", "colour_blind", "soft"] as const;

/** ACC-01/02/03/06: theme, text size (100-200%), dyslexia font, line spacing, read-aloud, reduce motion. */
export default function A11yPanel({ compact }: { compact?: boolean }) {
  const { user, savePrefs, t } = useSession();
  const a = user?.accessibility;
  const theme = user?.theme || (typeof document !== "undefined" ? document.documentElement.dataset.theme : "light") || "light";
  const hc = typeof document !== "undefined" ? document.documentElement.dataset.hc : "dark";
  return (
    <div className="a11y">
      <fieldset>
        <legend>{t("theme")}</legend>
        <div className="chips">
          {THEME_LIST.map((k) => (
            <label key={k} className={`chip ${theme === k ? "on" : ""}`}>
              <input type="radio" name="theme" checked={theme === k} onChange={() => savePrefs({ theme: k })} />
              {theme === k ? "✓ " : ""}{t(`theme_${k}`)}
            </label>
          ))}
        </div>
        {theme === "high_contrast" && (
          <div className="chips" role="group" aria-label={t("hc_variant")}>
            {(["dark", "light"] as const).map((v) => (
              <label key={v} className={`chip ${hc === v ? "on" : ""}`}>
                <input type="radio" name="hc" checked={hc === v} onChange={() => savePrefs({ hc: v })} />
                {hc === v ? "✓ " : ""}{t(v === "dark" ? "hc_yellow" : "hc_black")}
              </label>
            ))}
          </div>
        )}
      </fieldset>

      <label className="field">
        <span>{t("text_size")}: {a?.text_size ?? 100}%</span>
        <input type="range" min={100} max={200} step={10} value={a?.text_size ?? 100}
          onChange={(e) => savePrefs({ text_size: Number(e.target.value) })} aria-valuetext={`${a?.text_size ?? 100}%`} />
      </label>

      {!compact && (
        <label className="field">
          <span>{t("line_spacing")}: {(a?.line_spacing ?? 1.5).toFixed(1)}</span>
          <input type="range" min={1} max={2.5} step={0.1} value={a?.line_spacing ?? 1.5}
            onChange={(e) => savePrefs({ line_spacing: Number(e.target.value) })} />
        </label>
      )}

      <label className="switch"><input type="checkbox" checked={!!a?.dyslexia_font} onChange={(e) => savePrefs({ dyslexia_font: e.target.checked })} /> {t("dyslexia_font")}</label>
      <label className="switch"><input type="checkbox" checked={!!a?.reduce_motion} onChange={(e) => savePrefs({ reduce_motion: e.target.checked })} /> {t("reduce_motion")}</label>
      <label className="switch">
        <input type="checkbox" checked={!!a?.read_aloud} onChange={(e) => savePrefs({ read_aloud: e.target.checked })} /> {t("read_aloud")}
      </label>
      {a?.read_aloud && !speechSupported() && <p className="muted small">{t("read_aloud_unsupported")}</p>}
    </div>
  );
}
