# Administrator Guide

Admins can do everything a teacher can, for all subjects, plus manage students, teachers, classes, subjects, exams and settings. A Super Admin can also create or remove Admin accounts and permanently delete data. **Nobody marks answers by hand, and nobody edits an individual score.** Corrections happen by voiding a faulty question (everything recalculates) or by granting a retake.

## 1. Set up (once per year or term)
1. **Academic year and terms** (ADM-04), **classes and streams**, **subjects**.
2. **Teachers:** create accounts (strong password required), assign subjects and classes.
3. **Students, in bulk (AUTH-02..06):**
   - Download the template (columns: first name, last name, index number, class or form, stream).
   - Upload the Excel or CSV file. The system **validates** and shows a report of duplicate index numbers, missing fields and bad rows. Nothing is created until you **confirm**.
   - Accounts are created automatically. Username = first name in lowercase with no spaces (`amina`, `amina2`). First password = index number; the student must change it at first login.
   - Download the **printable credentials sheet** (PDF) per class.
4. **Settings (ADM-09):** school name and logo, grading scale, rules text, result delay (default 5 minutes), late-entry window (default 10), default theme and language, leaderboard on/off, class position on/off, question approval on/off.

## 2. Gamification settings
`/api/gamification/settings/` lets you change XP values, level names and XP needed, badge targets (bronze, silver, gold), the number of streak freezes per month (default 2), and how many practice quizzes per day can earn XP (default 5, so nobody can farm XP). `{"reset": true}` restores the SRS defaults. Changes affect awards from then on. XP already earned is kept.

**Decisions the school must make** (SRS section 10): leaderboard on or off (recommended: on, class level, weekly); show class position on results or not.

## 3. Running an exam
1. Check the paper has questions and is **Approved**.
2. **Schedule** it: date, start and end times (or duration), pass mark, rules, classes/streams/students. Several exams can form a timetable; each subject is its own exam with its own window.
3. **During the exam** use the **live monitor**: counts of online, not started, in progress, submitted; names of students who have not started (so staff can help); connection-problem indicators.
4. **Special cases:** grant **extra time** (for example after a power cut) or a **retake** for one student. A reason is required and it is written to the audit log. A retake is possible **only** when an admin grants it.
5. **Faulty question after the exam:** **void** it. All affected results are recalculated before publishing.
6. **Results publish automatically** at exam end + the result delay. A scheduled job also pays XP, streaks and badges after publishing.
7. Nobody (including you) can see results before the publish time.

## 4. Other duties
- **Announcements** to all students, a class or a stream.
- **Reset a password** for any student or teacher. Deleting a student **archives** them (restorable). Only a Super Admin deletes permanently.
- **Audit log:** who did what and when (logins, edits, deletions, password resets, retakes, extra time, voids). It cannot be edited.
- **Exports:** results, student lists and result slips to Excel and PDF.
- **School analytics:** by subject, class, stream and term; participation; engagement (streaks, XP, practice).

## 5. Technical operation (NFR-06, NFR-11)
- **Server start:** `gunicorn config.wsgi`. **Scheduler:** a cron job **every minute** running `python manage.py run_scheduler` (closes exams, publishes results, sends reminders, pays rewards).
- **Environment variables:** `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL` (PostgreSQL), `REDIS_URL`, `CORS_ORIGINS`, `DJANGO_CSRF_ORIGINS`, `MEDIA_ROOT` (a persistent disk), and for push: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CONTACT_EMAIL`.
- **Backups:** turn on automatic daily PostgreSQL backups with point-in-time recovery at your host. **Test a restore** at least once before go-live and write the steps in your own words. Back up the media folder (question images and logo) too.
- **Restore (outline):** create a new database from the backup, set `DATABASE_URL` to it, run `python manage.py migrate` (should say "No migrations to apply"), run `python manage.py golive_check`, then open the site.
- **Health check:** `python manage.py golive_check` prints PASS, WARN and FAIL lines.


## Parents and login messages
See `PARENTS_SMS.md` for how to upload parents' phone numbers, link them to students and send each child's login details by SMS from the school phone.
