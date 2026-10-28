"use client";
import PublicPage from "@/components/PublicPage";
import { useSession } from "@/lib/session";
import { SITE } from "@/lib/site";

export default function Accessibility() {
  const { t } = useSession();
  return (
    <PublicPage title={t("access_title")} updated>
      <p>{SITE.school} wants every student to be able to sit exams comfortably, whatever device, eyesight or reading needs she has. This page lists what {SITE.app} offers and where it still falls short.</p>

      <h2>What you can change</h2>
      <p>Open the <b>Accessibility</b> button (the person icon at the top) at any time, even on the login screen of the app after you sign in.</p>
      <ul>
        <li><b>Five themes:</b> Light, Dark, High contrast (yellow on black, or black on white), Colour-blind safe, and Soft low-glare.</li>
        <li><b>Text size</b> from 100% to 200%, and adjustable <b>line spacing</b>.</li>
        <li><b>Dyslexia-friendly font</b> and wider letter spacing.</li>
        <li><b>Reduce motion</b> to switch off animations. It also follows your device setting.</li>
        <li><b>Read aloud</b> for questions, using your device’s voice.</li>
        <li><b>Language:</b> English or Kiswahili.</li>
      </ul>

      <h2>Built in</h2>
      <ul>
        <li>Large touch targets and one question per screen, to reduce mistakes on small phones.</li>
        <li>Works with the keyboard alone, with visible focus outlines, and a “Skip to content” link.</li>
        <li>Labels and roles for screen readers on buttons, menus, tabs, timers and warnings.</li>
        <li>Every question image carries a description, and images can be zoomed.</li>
        <li>Meaning is never shown by colour alone: correct and wrong answers also use words and symbols.</li>
        <li>Timer warnings use text, with optional sound and vibration.</li>
      </ul>

      <h2>Known limits</h2>
      <ul>
        <li>Staff screens (question editor, exam builder, analytics) are in English only.</li>
        <li>Complex formulas written by teachers may not be read well by every screen reader. Ask the teacher for a text description if needed.</li>
        <li>Read aloud depends on the voices installed on your device, and Kiswahili voices are missing on some phones.</li>
      </ul>

      <h2>Extra support for exams</h2>
      <p>If a student needs extra time, a reader or another adjustment, ask your teacher or the administrator before the exam. Administrators can grant extra time, and every change is recorded.</p>

      <h2>Tell us about a problem</h2>
      <p>If something is hard to use, please tell us: <a href={`mailto:${SITE.email}`}>{SITE.email}</a> or {SITE.phone}. Say which page, which device and what happened, and we will work on it.</p>
    </PublicPage>
  );
}
