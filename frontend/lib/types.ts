export type User = {
  id: number; username: string; first_name: string; last_name: string; role: string; class: string | null;
  must_change_password: boolean; language: "en" | "sw"; theme: string;
  accessibility: { text_size: number; line_spacing: number; dyslexia_font: boolean; reduce_motion: boolean; read_aloud: boolean };
};
export type Opt = { id: string; text: string; image?: string | null; alt_text?: string };
export type Question = {
  id: number; type: "mcq_single" | "mcq_multi" | "true_false" | "matching" | "fill_blank" | "ordering";
  prompt: string; marks: number; content: any;
};
export type AttemptState = {
  attempt_id: number; exam_id: number; title: string; server_time: string; deadline_at: string; total_questions: number;
  warnings: number[]; status: string; finished: boolean; remaining_seconds?: number; index?: number; can_skip?: boolean;
  question?: Question | null; time_over?: boolean; results_at?: string; message?: string; results_note?: string;
  tips?: { kind: string; text: string }[];
  lock_reason?: "close" | "leaves" | "manual" | "";  // why it is locked
  locked?: boolean;  // sitting too close to another student: screen locked until an admin unlocks (clock keeps running)
};
export type ExamCard = {
  id: number; title: string; subject: string; start_at: string; end_at: string; duration_minutes: number; question_count: number;
  total_marks: number; rules_text: string; state: "upcoming" | "open" | "in_progress" | "done" | "missed"; attempt_id: number | null; server_time: string;
};
