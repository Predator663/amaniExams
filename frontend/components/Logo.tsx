import { CSSProperties } from "react";

/** The school crest, on a white disc so it stays readable on dark menus and in every theme. */
export default function Logo({ size = 40, label }: { size?: number; label?: string }) {
  const s: CSSProperties = { width: size, height: size };
  return (
    <span className="logo-img" style={s}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/logo.png" width={size} height={size} alt={label || ""} aria-hidden={label ? undefined : true} />
    </span>
  );
}
