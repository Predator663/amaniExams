# SRS section 10: sign-off sheet for school management

Please answer each question, then sign at the bottom. The right-hand column says what the system does **until you decide otherwise** and where the setting lives, so every answer can be applied without new development.

| # | Question | What the system does now | Your answer |
|---|---|---|---|
| 1 | How many students, which forms? | Sizes the server. The load test must use **at least twice** this number (NFR-05). Only O-Level (Form 1 to 4) is supported (GRD-01). | Students: ______  Forms: ______ |
| 2 | Is the NECTA O-Level scale (A 75-100, B 65-74, C 45-64, D 30-44, F 0-29; Division I 7-17, II 18-21, III 22-25, IV 26-33, 0 = 34+) and the **pass mark** right? | Scale is the default in Settings; pass mark is set per exam (`pass_mark_percent`). Published results keep the scale they were marked with, so changing it later never alters old results (GRD-04). | Scale OK? Y / N  Pass mark: ____ % |
| 3 | In which language is each subject examined? | Language is stored **per question** (English or Swahili). Interface is in both languages and each student picks hers. | Subject / language list: ______ |
| 4 | Written answers, working and practicals cannot be marked automatically. Accepted, or done on paper? | Only six auto-marked types exist: single choice, multiple choice, true/false, matching, fill-in-the-blank, ordering. | Accept / Paper for: ______ |
| 5 | Must an admin approve every teacher question? | Settings > `question_approval_required` (default **on**). | Yes / No |
| 6 | May students skip a question (never to return)? | Per exam `allow_skip` (default decided when the exam is built). | Yes / No |
| 7 | Leaderboard and class position on? | Settings > `leaderboard_enabled`, `show_class_position`. Leaderboard ranks **XP only**, never marks, and each girl can hide herself. | Leaderboard Y/N  Position Y/N |
| 8 | Late-entry window? | Settings > `late_entry_minutes` (default **10**). No time is added for late entry. | ____ minutes |
| 9 | Do some students share a phone? | One active login per student: logging in elsewhere ends the first session (AUTH-09). Tell students to **log out** after each use. Credential sheets list only girls who still have their starting password. | Yes / No / Some |
| 10 | Who pays for hosting, domain and SMS, and how long are results kept? | Hosting plan needs PostgreSQL, Redis, a persistent disk or object storage for images, and daily backups. **No automatic deletion is built**; the retention period you choose is applied by a Super Admin. Tanzania's Personal Data Protection Act applies (students are minors). | Pays: ______  Keep results: ____ years |

Also confirm (not in SRS section 10, but needed for go-live):
- Result delay after the exam closes (default 5 minutes, BR-06): ______ minutes
- Exam rules text shown before every exam: attached / default
- Who is the Super Admin (name, phone): ______
- Swahili wording has been read by a Kiswahili teacher: Y / N

Signed (Headteacher): ______________   Date: ________
Signed (Academic master/mistress): ______________   Date: ________

The go-live command prints which of these are still open: `python manage.py golive_check`.
