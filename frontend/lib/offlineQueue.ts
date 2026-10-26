/** EDAY-06: answers are kept on the phone until the server confirms them, so a refresh, a dropped network
 *  or a dead battery never loses an answer. The server ignores a repeated send of an answer it already has. */
export type Pending = { qid: number; response: any; skip: boolean };
const qKey = (attempt: number) => `amani_queue_${attempt}`;
const dKey = (attempt: number, qid: number) => `amani_draft_${attempt}_${qid}`;

export function readQueue(attempt: number): Pending[] {
  try { return JSON.parse(localStorage.getItem(qKey(attempt)) || "[]"); } catch { return []; }
}
export function enqueue(attempt: number, item: Pending) {
  const q = readQueue(attempt).filter((p) => p.qid !== item.qid);
  q.push(item);
  localStorage.setItem(qKey(attempt), JSON.stringify(q));
}
export function dequeue(attempt: number, qid: number) {
  localStorage.setItem(qKey(attempt), JSON.stringify(readQueue(attempt).filter((p) => p.qid !== qid)));
  localStorage.removeItem(dKey(attempt, qid));
}
export function saveDraft(attempt: number, qid: number, value: any) {
  try { localStorage.setItem(dKey(attempt, qid), JSON.stringify(value)); } catch { /* storage full: ignore */ }
}
export function readDraft(attempt: number, qid: number): any {
  try { const v = localStorage.getItem(dKey(attempt, qid)); return v === null ? undefined : JSON.parse(v); } catch { return undefined; }
}
export function clearAttempt(attempt: number) {
  for (let i = localStorage.length - 1; i >= 0; i--) {
    const k = localStorage.key(i);
    if (k && (k === qKey(attempt) || k.startsWith(`amani_draft_${attempt}_`))) localStorage.removeItem(k);
  }
}
