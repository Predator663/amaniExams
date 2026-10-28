/** ACC-03: read-aloud with the phone's own voices (English and Swahili where the device supports them). */
export const speechSupported = () => typeof window !== "undefined" && "speechSynthesis" in window;
export function htmlToText(html: string) {
  const d = document.createElement("div");
  d.innerHTML = html.replace(/<sup>/gi, " to the power ").replace(/<\/(p|li)>/gi, ". ");
  d.querySelectorAll("img").forEach((i) => i.replaceWith(document.createTextNode(` Image: ${i.getAttribute("alt") || ""}. `)));
  return (d.textContent || "").replace(/\s+/g, " ").trim();
}
export function speak(text: string, lang: string) {
  if (!speechSupported()) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = lang === "sw" ? "sw-TZ" : "en-GB";
  const voice = window.speechSynthesis.getVoices().find((v) => v.lang.toLowerCase().startsWith(lang === "sw" ? "sw" : "en"));
  if (voice) u.voice = voice;
  window.speechSynthesis.speak(u);
}
export const stopSpeaking = () => speechSupported() && window.speechSynthesis.cancel();
