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
   Optional: type an **Extra message** (up to 160 characters, e.g. a meeting date). It is added as the last line of every
   message, after the login details. *Check who will get a message* shows an example of the text and how many SMS it uses.
   Leave it empty to send only the login details. Curly quotes and dashes are made plain; emoji make each SMS shorter and dearer.

## Rules the system follows
- One message per parent. A student with two parents gets ONE password and both messages carry it.
- Children who have already changed their password, or who already have a message queued/sent, are skipped. Tick
  *send again* to give them a NEW password and send once more.
- If a message fails and its text was already erased, *Retry* creates a new message with a new password.
- The phone paces itself (default 8 s between messages, 3 min rest every 30). Networks can block a SIM that sends many
  messages at once.
- WhatsApp: automatic WhatsApp needs the paid WhatsApp Business service, so only SMS is sent automatically. The
  "uses WhatsApp" flag is stored for a later one-tap feature.

## Linking parents while uploading students
The **student** template has optional columns `parent name, parent phone, parent relationship` (and the same three for `parent 2`). Students and their parents are then created and linked in one step; the SMS steps below work unchanged. A parent is identified by the phone number, so brothers and sisters on different rows with the same number share one parent, and a parent registered earlier is reused. The separate parents' template still works for parents of students who already exist.

## Editing the message, or sending only your own text
On the **Send** tab:
- The standard login message (Kiswahili and English) is shown in a box you can edit. Keep `{children}` (one line per child: name, user name, password) and `{url}` (the school web address); everything else is yours to change. **Restore the standard wording** puts the original back. Each parent gets the language saved on their record.
- Untick **Include the login details** to send only your own message (up to 459 characters, 3 SMS). No password is created or changed, children are not marked as "already sent", and the school web address is not needed. Use it for meetings, reminders or announcements.
- The optional "extra message" (160 characters) is still added as the last line when login details are included.
