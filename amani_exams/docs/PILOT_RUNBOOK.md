# Pilot exam runbook (one class)

Do this on the **real server** with the **real database**, with one class, one short exam, before the whole school.

## 1. One week before
1. Server ready: PostgreSQL, `REDIS_URL` (**required** for the online counter and live monitor when the server has more than one worker), persistent disk or object storage for images, daily backups on, HTTPS. Run `python manage.py golive_check`: no FAIL lines.
2. Render cron job every minute: `python manage.py run_scheduler`.
3. Frontend built with `NEXT_PUBLIC_API_URL` pointing at the API and deployed (see `frontend/README.md`). API `CORS_ORIGINS` contains the frontend address.
4. Super Admin created. Settings filled in (school name, logo, rules text, result delay 5 min). Sign-off sheet (docs/SRS_SECTION10_SIGNOFF.md) signed.
5. Load test on a **separate test server** of the same size (see `loadtest/README.md`). Must print PASSED with at least twice the real enrolment. Use `--ramp 0` once. Never run it on the school database.
6. Teachers write 10 to 20 questions in the editor; admin approves them. Mark some questions "practice eligible".

## 2. Three days before
1. Bulk-upload the pilot class (validate, read the report, confirm). Download and print the credential sheet; hand each girl her own slip.
2. Schedule the exam (window 60 to 90 minutes longer than the duration, late entry 10 min). Select the pilot class.
3. Send an announcement with the date and "install the app" instructions.
4. Girls log in once at school/home **before the exam day**, choose a new password, install the app, and try the Practice demo.

## 3. Exam day (admin watches the live monitor)
- 15 min before: check "not started" list; help girls who are not logged in.
- During: watch "connection problems"; do not edit anything (a live exam cannot be edited).
- After close: results publish automatically at end + 5 min. Check one girl's result page, review mode and PDF slip.

## 4. Acceptance checks (SRS 9.2): tick each on the pilot
- [ ] A girl cannot open another girl's result by changing the link.
- [ ] Changing the phone clock or refreshing gives no extra time.
- [ ] Switch off data in the middle: she resumes at the same question with the right time left, and queued answers sync.
- [ ] Nobody sees results before the publish time; they appear on their own at end + 5 min.
- [ ] Teachers cannot upload question files or change marks.
- [ ] Works on iPhone Safari, a low-end Android phone and a computer, in Light, Dark, High contrast.
- [ ] Bulk upload of 500 rows validates and creates accounts in under a minute (test on the test server).

## 5. After
Collect problems from girls and teachers, fix, then go-live for all classes. Keep the backup restore test (restore yesterday's backup to a test database) on the calendar.
