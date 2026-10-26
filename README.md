# Amani Girls Exam System: backend (Phases 1, 2 and 3)

Django REST Framework API for SRS v1.1. Phase 1 core exams, Phase 2 teacher/admin portals and analytics, and
**Phase 3: gamification (XP, levels, streaks, badges, leaderboard, practice mode), Swahili, exam-finish tips,
load testing, user guides, training, pilot and go-live tools**.

> **Status (Phase 4):** all 122 tests pass (`python manage.py test`, about 2 seconds) and `makemigrations --check` says
> "No changes detected". The web app is in `frontend/` (see `frontend/README.md`). Phase 4 was also checked end to end
> in a real browser against this API: login, exam with an offline interruption, results, review, analytics, badges,
> practice, notifications. Real-world steps (pilot, sign-off, load test on your server) are in `docs/`.

## Phase 4 changes to the backend
- Fixed the failing test: a 100% score is also the top grade, so the **Subject Star** badge is correctly earned (the test expected 3 badges, now 4).
- Tests use a fast password hasher, so the suite runs in 2 seconds instead of 3 minutes (real hashers are untouched).
- Preferred password hasher is now PBKDF2-SHA256 with 600,000 iterations (OWASP recommendation) instead of Django's 1,000,000: about 30% less processor time per login. Old hashes still work and upgrade on the next login.
- Load test findings (60 students, `--ramp 0`, 1 CPU core, 3 gunicorn workers): with **PostgreSQL** 0 errors and answers saved in about 14 ms; with SQLite 25 students got HTTP 500 (database locked), so **never use SQLite for exams**. Login is the heavy part (password hashing), roughly 0.2 s of processor time each: for 500 students logging in the same minute use at least 4 cores, or have students log in before the exam (the login stays valid).

## Run it on your own computer (Windows or Linux)
Two terminals. Nothing to configure: `runserver` is treated as development automatically (plain http, any origin allowed).

```
:: terminal 1 - the API
venv\Scripts\activate
python manage.py migrate
python manage.py createsuperuser        (or create an admin in the Django admin)
python manage.py runserver              (http://localhost:8000)

:: terminal 2 - the web app
cd frontend
npm install
npm run dev                             (http://localhost:3000)
```

**Login says it cannot reach the server?** Cause found and fixed in Phase 4: with `DJANGO_DEBUG` unset the API forced every request to redirect to `https://`, which does not exist locally (the browser shows 301/blocked CORS preflight). Now `python manage.py runserver` turns debug on by itself. If you start the API any other way (gunicorn, `waitress`), set `DJANGO_DEBUG=1 DJANGO_SSL_REDIRECT=0` for local use. A `304` in the browser's network tab is only "not modified" (cached file) and is harmless. If the web app is not on the same computer, set `NEXT_PUBLIC_API_URL=http://<computer-ip>:8000` before `npm run dev`.
**Production** (gunicorn): `DJANGO_DEBUG=0`, `CORS_ORIGINS=https://your-web-app-address`, `DJANGO_ALLOWED_HOSTS=your-api-address`.

## First run (important change: migrations)
Phase 1 shipped without `migrations/` folders, so `makemigrations` said "No changes detected" and only Django's own
tables were created. Every app now has an empty `migrations/` package, so:

```bash
pip install -r requirements.txt
python manage.py migrate            # includes the new gamification app (its migration is included)
python manage.py makemigrations --check --dry-run   # should say: No changes detected (type only the command; on Windows do not paste the # comment)
python manage.py test               # Phase 1 + 2 + 3 tests
PYTHONPATH=. python -m unittest gamification.test_rules   # pure rules, no Django needed
python manage.py createsuperuser    # then set role=super_admin in /django-admin/
python manage.py runserver
```
If `makemigrations` complains about a circular dependency, run it per app in this order:
`python manage.py makemigrations academics accounts core questions exams notifications`.
If you already ran `migrate` on a database, nothing of yours is lost: the app tables did not exist yet.

### The 3 failures + 1 error you saw in Phase 1
All four had one cause: with `DEBUG` off, `SECURE_SSL_REDIRECT` made the test client get `301` instead of `400/404`
(and the HTML redirect page broke `.json()`). Fixed in `config/settings.py`: the redirect is skipped under
`manage.py test`. The "No directory at: staticfiles" warning is harmless (run `collectstatic` on Render).

## Environment (Render)
`DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL` (PostgreSQL), `REDIS_URL` (optional), `CORS_ORIGINS`,
`DJANGO_CSRF_ORIGINS`. Optional Web Push: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CONTACT_EMAIL` + `pip install pywebpush`.
Start command: `gunicorn config.wsgi`. Render cron job **every minute**: `python manage.py run_scheduler`
(closes exams, publishes results, and now also creates the 1-day / 1-hour / exam-start notifications).
Warning: question images and the school logo are saved to disk; Render's disk is wiped on every deploy, so before
go-live use object storage or a persistent disk (SRS section 8).

## What Phase 2 added, by SRS requirement
| SRS | Where |
|---|---|
| TCH-01..03, 05, 06, 08 teacher dashboard, student list/profile, question analysis, heat map; only published results; scoped to assigned subject + class | `analytics/views.py`, maths in `analytics/calc.py` |
| TCH-04 flags (needs support / top performer) | `calc.flag_for` (thresholds at the top of `calc.py`) |
| TCH-09, ADM-11 PDF + Excel exports | `core/reports.py`, `analytics/views.py` (`?file=pdf` or `xlsx`) |
| RES-04, GRD-02, GRD-03 student analytics, best-seven report card, projected division | `student/analytics/`, `student/report-card/` |
| RES-06 PDF result slip (own, after publish); admin slip | `results/<attempt>/slip/`, `exports/slip/<attempt>/` |
| AUTH-06 credential sheet PDF per class | `students/bulk-upload/<id>/credentials/`, `students/credentials/?class=` |
| AUTH-07, ADM-03 teacher accounts, strong passwords, reset | `teachers/` (+ `reset-password`) |
| Super Admin creates/removes Admins | `admins/` (super admin only) |
| ADM-01/02 deactivate, graduate, move class, bulk actions | `students/<id>/{deactivate,activate,graduate,move}/`, `students/bulk-action/` |
| ADM-04 academic years and terms (exams can carry a term) | `academic-years/`, `terms/` |
| ADM-06 connection-problem indicators in live monitor | `exams/<id>/monitor/` (needs the 30 s `presence/` heartbeat) |
| ADM-07 unschedule, close early (needs `confirm` + reason) | `exams/<id>/unschedule/`, `exams/<id>/close/` |
| ADM-08 school analytics | `analytics/school/` |
| ADM-09 validated settings (grade scale checked for gaps/overlaps), logo | `settings/`, `settings/logo/` |
| ADM-10 audit filters + paging | `audit-log/?actor=&action=&from=&to=&limit=&offset=` (now returns `{count, results}`) |
| NOT-01..03 in-app, Web Push, announcements | `notifications/` app |
| ACC-01/02/03/06 preferences saved per user | `PATCH /api/me/` (`theme`, `text_size` 100-200, `line_spacing`, `dyslexia_font`, `reduce_motion`, `read_aloud`) |
| EDAY-11 integrity flags for staff after publish | `analytics/exams/<id>/integrity/` |

## API additions (all under `/api/`, header `Authorization: Token <key>`)
Staff: `analytics/subjects/`, `.../<id>/` (+ `students/`, `students/<sid>/`, `heatmap/`, `export/`), `analytics/exams/<id>/{questions,integrity}/`
Admin: `analytics/school/`, `teachers/`, `admins/` (super admin), `students/bulk-action/`, `students/credentials/`, `academic-years/`, `terms/`,
`announcements/`, `settings/logo/`, `exports/{students,exams/<id>/results,slip/<attempt>}/`
Everyone: `notifications/` (+ `read/`), `push/{public-key,subscribe,unsubscribe}/`; students: `student/analytics/`, `student/report-card/`, `results/<attempt>/slip/`

## Notes and decisions
- Downloads use `?file=pdf|xlsx|csv` (not `?format=`, which DRF reserves). The API ignores the browser's `Accept` header.
- Retakes: analytics count a student's latest attempt per exam.
- Report cards use the grade scale saved with the student's most recent result (GRD-04), so editing the scale later never rewrites history.
- Notifications are created by the scheduler **and** lazily when a student opens her notifications, so a missed cron run never loses a reminder.
- Excel and CSV cells are written as text, so a name starting with `=` can never run as a formula.

## What Phase 3 added, by SRS requirement
| SRS | Where |
|---|---|
| 5.1 XP table (all values admin-editable) | `gamification/rules.py` (`DEFAULT_XP`), `services.reward_attempt` |
| 5.2 Levels 1-7 with progress bar data and level-up flag | `rules.level_for`, `GET gamification/me/`, `POST gamification/ack/` |
| 5.3 Daily streak, 2 freezes per month, exam streak, kind restart message | `rules.compute_runs / streak_status / exam_streak` (worked out from the set of learning days, so order can never corrupt it) |
| 5.4 Ten badges with bronze/silver/gold, unlock flag, cabinet with next goals | `gamification/catalog.py`, `GET gamification/badges/` |
| 5.5 Practice mode (instant feedback, XP, streak, per-subject switch, never exam marks) | `practice/...` endpoints, `PracticeSession` |
| 5.6 Profile (avatar, display name), class-level weekly leaderboard, hide myself | `gamification/profile/`, `gamification/leaderboard/` |
| BR-10 rewards only after publish, never change marks | `reward_attempt` refuses until the exam is Published and her result is visible |
| RES-03 XP and badges on the result page | `GET results/<attempt>/` now has a `rewards` block |
| RES-05 + Mistake Master / review XP | `GET/POST results/<attempt>/review/seen/` |
| TCH-03 streak + practice activity; ADM-08 engagement | `analytics/` student profile, student list, `analytics/school/` |
| ADM-09 XP values, levels, badge targets, freezes, practice limit | `GET/PATCH gamification/settings/` (`{"reset": true}` restores defaults) |
| ACC-08 / NFR-10 Swahili | `core/i18n.py`: notifications, exam-finish messages, XP labels, badge/level names follow `user.language`; `GET i18n/<en|sw>/` gives the app the same text |
| EDAY-09 tips and tricks on the finish screen | `core/tips.py`, `tips` in the finished attempt state |
| NFR-05 load testing | `loadtest/` + `manage.py seed_loadtest` |
| Pilot and go-live | `manage.py golive_check`, `docs/pilot_and_golive.md` |
| NFR-09 user guides, training | `docs/` (student guide in English and Kiswahili, teacher, admin, training plan) |

## New API (all under `/api/`)
Student: `gamification/{me,ack,badges,xp,profile,leaderboard,catalog}/`, `practice/subjects/`, `practice/start/`, `practice/<id>/`, `practice/<id>/answer/`, `results/<attempt>/review/seen/`
Staff: `practice/subjects/<id>/toggle/` (teacher: own subjects), `practice/mark-eligible/`
Admin: `gamification/settings/`
Public: `i18n/<lang>/`

## Decisions I made (change them if the school disagrees)
- **Rewards are paid lazily and by cron.** The scheduler (`run_scheduler`) pays XP/streaks/badges after publish; the home page and result page also pay anything due, so a missed cron run loses nothing. Each exam is processed once per student (`ExamRewardMark`) and each XP line has a unique key.
- **Only the first attempt earns XP.** A retake (admin-granted, for example after a power cut) earns nothing, so XP cannot be collected twice.
- **Exam day counts for the streak when results publish** (dated by the day she sat the exam), to respect BR-10.
- **Bronze = the SRS rule** (for example Practice Pro bronze = 50 quizzes); silver and gold are my higher targets. On Fire gold is shown as "Unstoppable" (30 days). All-Rounder needs results in at least 3 subjects in a term that has ended, with every subject average at B or better.
- **Practice:** 5 to 20 questions; a question that sits in any exam whose results are not yet published is never offered; at most 5 XP-earning quizzes per day (admin-editable) so nobody farms XP.
- **Leaderboard:** class level only; weekly (Monday 00:00 EAT) or all-time; students with 0 XP are not listed; ids are never sent.
- **Swahili text** (including the Kiswahili guide) should be checked by a Kiswahili teacher.
- `LOGIN_THROTTLE_RATE` env var (default `20/min`) exists only so load tests from one IP are possible.

## Still not built
The **React/Next.js PWA front end** (screens, themes, read-aloud, service worker, installability, offline answer queue). The API stores and serves everything it needs. Also not possible from code: the pilot exam itself, school sign-off of the SRS section 10 questions, and a real load test on your server.
