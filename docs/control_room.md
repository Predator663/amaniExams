# Control room (owner only)

Open **`/controlroom/`** on the Django server (also listed as *Control room* in `/django-admin/`). Sign in at `/django-admin/login/` first.

## Set up once
On Render set the environment variable **`CONTROLROOM_OWNERS`** to your own user name (for example `goose`). Only that account counts as the owner.
If it is empty, any superuser is treated as an owner. Then run `python manage.py migrate`.

## Turn the whole site off (maintenance mode)
1. Open the Control room. Optionally write a message and a "back at" time. Tick *sign out everyone* to end every current login.
2. Type the three random words shown (they change every time and are valid for 5 minutes, one try each). A wrong try changes nothing.
3. The site is now off for everybody: the web app shows a maintenance screen, the API answers 503, parents' SMS sending is paused.
4. Only **you** get in: sign in to the web app with your own user name as usual (nobody else can sign in), and open `/django-admin/` and `/controlroom/`.
5. **Bring the site back online** is one click.

If you ever lose access to the page, on the server run `python manage.py maintenance off` (also `on`, `status`).
To keep the SMS phone working during maintenance set `CONTROLROOM_EXEMPT_PREFIXES=["/api/sms/"]` in `config/settings.py`.

## God's Eye (`/controlroom/eye/`)
Refreshes every 10 seconds: accounts, who is online right now, the SMS queue, the audit trail, recent sign-ins, admin changes and the number of rows in every table.
`/controlroom/eye/tables/` opens any table, read-only, with search and pages. Passwords, login tokens, keys and encrypted data (parents' phone numbers, SMS text) always show as "hidden".

Every switch is recorded (who, when, from which address) and visible under *Control events* in the Django admin.
