# Pilot Exam and Go-Live Plan (SRS 9.1 Phase 3)

## Before the pilot
1. On the real server: `python manage.py migrate`, then `python manage.py golive_check`. Fix every FAIL; read every WARN.
2. **Load test on a test copy** (never the real database): see `loadtest/README.md`. Passing means every student logged in and started without errors and saving an answer stayed under about 1 second (p95).
3. Ask the school to confirm in writing the open questions of SRS section 10 (scale and pass mark, languages per subject, approval, skipping, leaderboard, late-entry window, shared phones, hosting and data retention).
4. Train people (`training_plan.md`). Send the parents' letter.
5. Choose **one class** and **one short exam** (20-30 questions, 30-40 minutes) in a subject that suits automatic marking.

## Pilot day
- Have a teacher or admin watching the **live monitor** and a phone number students can call.
- Keep a list of problems (device, browser, what happened).
- After results publish (+5 minutes): check results appear automatically, XP and badges appear, notifications arrive, PDF slips download, teacher analytics look sensible.

## Pass criteria (SRS 9.2: the system is accepted only when ALL pass)
| # | Acceptance test | How to check |
|---|---|---|
| 1 | A student cannot reach another student's data by changing links | Log in as student A, try student B's result id in the address: must be "not found" |
| 2 | Changing the phone clock or refreshing gives no extra time | Change the clock, refresh; the timer must not move |
| 3 | After refresh, disconnection or restart the student resumes at the same question with the right time left | Switch airplane mode on and off mid-exam; close and reopen the browser |
| 4 | Results are invisible before the publish time and appear at exam end + 5 minutes | Ask a student to look at minute 4 and minute 6 |
| 5 | Teachers cannot upload question files or change marks | Try as a teacher: no such option and the server refuses |
| 6 | A bulk upload of 500 students validates and creates accounts in under a minute, with a clear error report for bad rows | Time a 500-row file that includes 3 bad rows |
| 7 | Exam and results screens work on iPhone Safari, low-end Android and desktop, in all themes | Try each device and theme |
| 8 | A full-school simultaneous login and exam start works without errors in load testing | `loadtest/run_load.py` says PASSED |
(Automated tests for 1-5 are in the code: `python manage.py test`.)

## After the pilot
Fix the problem list, run the load test again, brief everyone, then schedule the first real exam. Keep the old process (paper) ready for the first real exam as a safety net.

## Go-live day
- Scheduler cron job running every minute. Backups on. `golive_check` shows no FAIL.
- A named person on call during every exam window for the first term.
- Afterwards: review the audit log and the problem list; decide what to improve.
