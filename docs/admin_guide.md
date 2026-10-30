# Administrator Guide

Admins can do everything a teacher can, for all subjects, plus manage students, teachers, classes, subjects, exams and settings. A Super Admin can also create or remove Admin accounts and permanently delete data. **Nobody marks answers by hand, and nobody edits an individual score.** Corrections happen by voiding a faulty question (everything recalculates) or by granting a retake.

## 1. Set up (once per year or term)
1. **Academic year and terms** (ADM-04), **classes and streams**, **subjects**.
2. **Teachers:** create accounts (strong password required), assign subjects and classes.
3. **Students, in bulk (AUTH-02..06):**
   - Download the template (columns: first name, last name, index number, class or form, stream, and the optional parent columns: parent name, parent phone, parent relationship, parent 2 name, parent 2 phone, parent 2 relationship).
   - **Parents are linked automatically.** Fill the parent columns on each student's row. A parent with several children is simply written on each child's row with the **same phone number** (any format: 0712 345 678, +255712345678, 712345678) and becomes ONE parent linked to all of them; a parent who is already registered is reused. The name may be left empty on later rows. The parent columns are optional: rows without them create students only, and parents can still be added later under Parents. A wrong phone number is reported on its row and that student is not created until the row is fixed. Parents' numbers are stored encrypted (needs `GUARDIAN_KEY`).
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
   - **Anti-cheat tab (Live monitor):** plan view of every writing student from her phone's position (GPS/Wi-Fi fused by the phone, plus motion). Hover or tap a dot for her name and status; a blue pulse means she is moving; students under 20 m apart turn red, are joined by a line and trigger a sound, a banner and a notification. Use **Locate** to zoom to the pair, check the reading ("precise" or "rough position"), speak to the students, then **Mark reviewed** (recorded in the audit log). An alert is information, not proof (siblings and neighbours can live close). Students without a position, or with Location blocked, are listed under "No location signal".
   - Place names (street, district, country) in the tooltip and alerts come from `GEOCODER_URL` (default OpenStreetMap Nominatim; set it empty to switch off, or point it at your own Nominatim server). The alert distance and the exam lock are set in the app, not in the environment: **Settings → School → Anti-cheat**. Settings (environment variables): `PROCTORING_ENABLED` (default 1), `LOCATION_MAX_ACCURACY` (default 100 m, rougher fixes are not compared). Run `python manage.py purge_locations` daily to delete stored positions of finished exams.
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


### Alert distance and locking students who sit too close
- **Settings → School → Anti-cheat** sets the alert distance in metres (1–500, default 20). It applies at once, also to exams that are running.
- Tick **Lock the exam of students who sit closer than this distance** to lock both students when a precise position confirms they are too close. They see a banner telling them to move apart and cannot answer. Their timer keeps running, no time is added, and answers they had already typed are kept on the phone and sent after the unlock.
- Unlock in **Live monitor → Anti-cheat**: **Unlock** next to a pair, or **Unlock all**. Moving apart does not unlock by itself. Unlocking a pair that is still close does not lock them again; if they part and later sit close again, a new alert locks them again.
- Rough positions (indoors, weak sky view) only raise an alert, they never lock. Switching the option off releases everyone who is locked. Locks and unlocks are written to the audit log (`proximity_lock`, `proximity_unlock`).


### Leaving the exam screen: count, automatic lock, manual lock
- Every time a student switches app, tab or screen during an exam it is counted and shown in **Live monitor → Writing** (for example *left screen ×2 (2/3 allowed)*).
- **Settings → School → Anti-cheat: leaving the exam screen** has two controls: the automatic lock (on by default) and **Times she may leave** (default 3, you can set 0–50). With 3, the first three exits only warn her on screen; the fourth locks her exam. A locked student sees a lock screen, cannot answer, and her timer keeps running (no extra time). Her answers are safe.
- Administrators are notified when someone is locked this way. In **Live monitor → Writing** a locked student shows 🔒 and an **Unlock** button; every writing student has a **Lock** button for a manual lock (the lock stays until you unlock, whatever the settings).
- **Unlock** gives her a fresh allowance (her earlier exits stay on the record but no longer count). **Unlock all** in the Anti-cheat tab also releases these locks. Switching the automatic lock off releases students locked by it; manual locks stay.
- Leaving the screen can be innocent (a phone call, a notification that pulls the app away). Look at the count and talk to the student before you decide; the lock is a prompt for you, not a verdict.

### Device and position checks (Live monitor → Anti-cheat → "Device and position checks")
These are signs to look at, never proof. Nothing is blocked or changed automatically; you review each one and press **Mark reviewed**
(if the same sign happens again it shows up again). *High* and *check* flags page the administrators once; *info* flags do not.
- **Device changed**: the exam is now sent from another device than at the start. Each browser makes a random code for itself.
  *High* when the new device is another kind (for example Android → Windows) or on another network; *check* when it looks like the same
  phone with a new code (browser data cleared, or the installed app and the browser mixed up).
- **Logged in again** (info): the student logged in again while writing, which ends her first session. Common when a phone restarts;
  it matters when it comes with *Device changed*.
- **Position jumped** (high): two precise positions further apart than any vehicle could travel in the time between them.
- **Position never moves**: exactly the same precise position and accuracy for about a minute. Real GPS always drifts a little.
- **Impossible accuracy**: ±1 m several times in a row, which no phone reaches indoors.
- **Typed-in coordinates**: round coordinates (at most 4 decimals) several times in a row.
Rough positions (poor accuracy) are ignored by the position checks, because switching between Wi-Fi and satellite positioning really does
jump around. Limits of the web app: it cannot see a fake-location app directly, and a student who clears the browser's data gets a new
device code. Flags are kept 180 days (`python manage.py purge_locations --flag-days N`). The Privacy policy and Terms were updated and
`LEGAL_VERSION` is now 2026-10-29, so students accept the new text before their next exam.


### Related students (twins, same house, same room)
- In Live monitor → Anti-cheat, open **Related students** under the map. Pick 2 to 8 students, choose *Twins*, *Same house* or *Same room*, and press **Mark as related**
  (every pair among them is marked). You can also use **Mark as related…** on an alert; that ends the alert and unlocks them at once.
- When a related pair is close (inside the alert distance) the map shows a dashed line with the kind written above it, and the side list shows them under
  "Related students close together". They raise **no alert** and are **never locked**. A third student who sits close to one of them is still alerted.
- **Remove** a pair in the same panel and alerts apply to them again. Marking and removing are written to the audit log.

### Messages to one account
- **Messages** (Administration menu) sends a message to 1–30 students or teachers; the Anti-cheat tab has a **Message** button on every alert and check.
- The person sees it as a banner at the very top of the screen, also during an exam and over the lock screen. One tap closes the banner; the message then stays in
  her **Messages** tab. She cannot delete it. When you **Delete** it on the Messages page it disappears from her tab (and banner) too. The page shows who has closed the banner.
- Students in an exam receive the banner within about 6 seconds; other pages check every 20 seconds.
