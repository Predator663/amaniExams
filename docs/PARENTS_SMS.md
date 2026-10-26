# Parents and login messages

The administrator can keep parents' contact details, link each parent to her children, and send each child's login
details to the parent as an SMS from the school phone.

## What is stored, and how it is protected
- Parent **name and phone number are encrypted** in the database (Fernet / AES). The key is the environment variable
  `GUARDIAN_KEY`. It is not in the database, so a stolen database or backup alone shows nothing.
  Create one: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. **Keep a copy somewhere safe**:
  without it the saved names and numbers can never be read again. `python manage.py golive_check` fails if parents
  exist and the key is not set.
- The website shows numbers hidden (`+255 7•• ••• 678`). *Show* reveals one for 15 seconds and is written to the audit log.
- The SMS holds a **random 8-letter password** (never the index number). It is erased from the database as soon as the
  phone reports the message as sent. The child must choose her own password at first login.
- Only administrators can use any of it. The phone uses a separate secret token (only its hash is stored).

## Steps
1. **Parents > Upload**: download the template, fill it (`parent_name, phone, relationship, student_index, whatsapp,
   language`), choose it, *Check the file*, then *Save*. Two daughters: `S0101;S0107` in one cell. The same phone number
   in two rows becomes one parent.
2. **Parents > Phone**: write the school's short web address, press *Create pairing code*, install the Android app
   (`android-sms-sender/`) on the school phone and pair it.
3. **Parents > Send**: *Check who will get a message*, then *Queue*. Watch the table: queued, sent, delivered, failed.
   *Retry all failed* tries again; *Cancel waiting* stops the rest.

## Rules the system follows
- One message per parent. A student with two parents gets ONE password and both messages carry it.
- Children who have already changed their password, or who already have a message queued/sent, are skipped. Tick
  *send again* to give them a NEW password and send once more.
- If a message fails and its text was already erased, *Retry* creates a new message with a new password.
- The phone paces itself (default 8 s between messages, 3 min rest every 30). Networks can block a SIM that sends many
  messages at once.
- WhatsApp: automatic WhatsApp needs the paid WhatsApp Business service, so only SMS is sent automatically. The
  "uses WhatsApp" flag is stored for a later one-tap feature.
