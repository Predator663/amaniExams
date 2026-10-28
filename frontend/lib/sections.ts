/** Paper sections. Mirrors exams/sections.py: grouped by question type in a fixed order; only used sections get a letter. */
export const SECTIONS: [string, string, string][] = [
  ["mcq_single", "Multiple choice (one answer)", "Choose the one correct answer."],
  ["mcq_multi", "Multiple choice (several answers)", "Choose every correct answer."],
  ["true_false", "True or false", "Say whether each statement is true or false."],
  ["matching", "Matching", "Match each item on the left with the correct item on the right."],
  ["fill_blank", "Fill in the blank", "Write the missing answer."],
  ["ordering", "Ordering", "Put the items in the correct order."],
];
export type Section<T> = { letter: string; qtype: string; title: string; instruction: string; items: T[]; marks: number };

export function groupSections<T extends { qtype: string; marks: number }>(items: T[]): Section<T>[] {
  const out: Section<T>[] = [];
  for (const [qtype, title, instruction] of SECTIONS) {
    const list = items.filter((x) => x.qtype === qtype);
    if (list.length) out.push({ letter: String.fromCharCode(65 + out.length), qtype, title, instruction, items: list, marks: list.reduce((a, x) => a + Number(x.marks || 0), 0) });
  }
  return out;
}
/** The order the server stores the paper in: section by section, picked order inside each section. */
export const canonicalOrder = <T extends { qtype: string; marks: number }>(items: T[]): T[] => groupSections(items).flatMap((s) => s.items);
