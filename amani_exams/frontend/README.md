# Amani Exams: web app (PWA)

Next.js 14 + React + TypeScript, built as **plain static files** (`output: "export"`), so it can be hosted anywhere. It talks to the Django API only.

## Run it
```bash
cd frontend
npm install
cp .env.example .env.local        # set NEXT_PUBLIC_API_URL to your API
npm run dev                       # http://localhost:3000
```
In development the web app forwards `/api` and `/media` to Django itself (default `http://127.0.0.1:8000`, change with `BACKEND_URL=http://127.0.0.1:9000 npm run dev`), so the browser only talks to one address: no CORS, and it also works from a phone on the same Wi-Fi (`http://<computer-ip>:3000`). You do **not** need a `.env` file.
**Cannot log in / "Cannot reach the server"?** Press **Test the connection** on the login screen: it says whether Django is not running, refuses the web app's address (CORS), or is on a different port.

## Deploy (Render Static Site)
Build command `npm install && npm run build`, publish directory `out`, environment `NEXT_PUBLIC_API_URL=https://YOUR-API` (and on the API `CORS_ORIGINS=https://YOUR-WEB-APP`). Serve over HTTPS (needed for the service worker and install). The address must be at the **root** of its domain (the service worker scope is `/`).

## What is here (SRS)
| Area | Where |
|---|---|
| Login, show-password, forced first password change (AUTH-01/05/10) | `app/login`, `app/change-password` |
| Home: swipeable exam banner with countdown, streak/XP/level/badges, online count, install guide, demo (HOME-01..05) | `app/page.tsx`, `components/ExamBanner.tsx`, `app/install`, `app/demo` |
| Exam: pre-exam screen, rules tick, one question at a time, server-timer display, warnings with sound/vibration, autosave + offline queue, resume, finish early, time over, tips (EDAY-01..12) | `app/exam/page.tsx`, `lib/offlineQueue.ts` |
| Six question types, images with alt text and zoom (QB-01..04) | `components/QuestionView.tsx`, `components/Rich.tsx` |
| Results, review, PDF slip, analytics, projected division (RES-01..06, GRD-03) | `app/result`, `app/review`, `app/progress` |
| XP, streaks, badge cabinet, leaderboard, practice, profile (SRS 5) | `app/badges`, `app/leaderboard`, `app/practice`, `app/settings` |
| Five themes + high-contrast variants, text size 100-200%, line spacing, dyslexia font, reduce motion, read-aloud (ACC) | `components/A11yPanel.tsx`, `components/Listen.tsx`, `app/globals.css` |
| English / Swahili (ACC-08) | `lib/i18n.ts` (+ server text from `/api/i18n/<lang>/`) |
| PWA: manifest, icons, service worker, Web Push (NFR-02, NOT-02) | `public/manifest.webmanifest`, `public/sw.js`, `app/settings` |
| Staff console: subject results, live monitor, bulk upload + credential sheet, announcements | `app/staff` |
| Question editor: six types, rich text, symbols, formula and chemical-formula editor, images with required alt text, phone/computer live preview, local autosave, duplicate warning, Draft → Submitted → Approved (QB-01..12) | `app/staff/questions`, `components/QuestionEditor.tsx`, `components/RichEditor.tsx` |
| Exam builder and scheduler: details, classes, East Africa Time window, options, pick questions or random rules, schedule/unschedule, timetable by day, close early, void a question, extra time or retake (EXM-01..09) | `app/staff/exams`, `components/ExamForm.tsx` |
| Settings (admins): school, logo, rules, result delay, late entry, themes, approval, leaderboard, class position, NECTA grading scale, XP/levels/badge targets, classes, subjects, practice on/off, years and terms (ADM-04, ADM-09, RES-07) | `app/staff/settings` |
| Live monitor: refreshes every 10 s (pause/resume), online now, progress and time left per student, connection problems, not started, submitted, class filter; teachers see numbers only (ADM-06, TCH-08) | `app/staff/monitor` |
| People: teacher and admin accounts, subject/class assignment, password reset (temporary password shown once), student list with search/filter, add, edit, move, deactivate, graduate, archive, restore, permanent delete (Super Admin), bulk actions, username sheets (ADM-01..03, AUTH-06/07) | `app/staff/people` |
| Audit log viewer with filters and paging, read-only (ADM-10) | `app/staff/audit` |
| School analytics: by subject, class, stream, term; participation; engagement (ADM-08) | `app/staff/school` |
| Teacher analytics: topic heat map, students with flags and profiles, question analysis, screen-leave flags, Excel/PDF export (TCH-02..06, TCH-09) | `app/staff/analytics` |

## Not built yet (use the API or Django admin for now)
A separate screen to view/edit a student's analytics as an admin (admins use the Analytics screen, which lists every student). Staff screens are in English only; student screens are in English and Swahili.

## Rules the code follows
- The server owns the clock: the timer only displays `deadline_at - server time`; at zero the app asks the server to close the attempt.
- Correct answers never reach the phone before results are published; the app never caches API responses (the service worker skips them).
- Answers are queued in `localStorage` until the server confirms them; a repeated send is ignored by the server.
- Swahili text should be read by a Kiswahili teacher before go-live.
