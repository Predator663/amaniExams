# Load testing

Goal (SRS NFR-05, acceptance test 9.2): every enrolled student can log in and start the exam in the same minute without errors, and saving an answer stays fast (about 1 second).

**Never run this against the real school database.** It creates fake students.

## Steps
1. Make a **test server** like the real one (same size, same PostgreSQL type) with its own empty database. Set `LOGIN_THROTTLE_RATE=100000/min` on that test server only (otherwise the login limit of 20 per minute blocks the test, because every fake student has the same internet address).
2. On the test server: `python manage.py migrate` then
   `python manage.py seed_loadtest --students 500 --questions 40 --yes`
   (use at least twice your real enrolment, as the SRS asks).
3. From any computer with Python 3.9+ (no packages needed):
   `python loadtest/run_load.py --base-url https://YOUR-TEST-SERVER --students 500 --ramp 10 --report result.json`
   For a harsh test use `--ramp 0` (everyone logs in at the same second).
4. Read the table. The last line says PASSED or FAILED and why. Run it 2-3 times.
5. Clean up: `python manage.py seed_loadtest --cleanup`.

## If it fails
- **Login slow:** password hashing uses a lot of processor time (by design). Use more than one worker (`gunicorn config.wsgi --workers 4`) or a bigger instance.
- **Errors with status 0 or 5xx:** the server ran out of memory or database connections. Check the host's logs. Add workers, raise the database connection limit, or use a bigger plan.
- **"students online" wrong:** set `REDIS_URL`.
- **Answers slow:** check the database is in the same region as the server.
