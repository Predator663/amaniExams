"use client";
import PublicPage from "@/components/PublicPage";
import { useSession } from "@/lib/session";
import { SITE } from "@/lib/site";

export default function Privacy() {
  const { t } = useSession();
  return (
    <PublicPage title={t("privacy_title")} updated>
      <div className="hint"><b>Muhtasari kwa Kiswahili.</b> Tunakusanya jina, namba ya mtihani, darasa, majibu na matokeo yako ili kuendesha mitihani ya shule. Hatuuzi taarifa zako, hatuna matangazo, na hatutumii wafuatiliaji wa nje. Matokeo yako huonekana kwako, kwa walimu wa masomo yako na kwa utawala wa shule tu. Mzazi au mlezi anaweza kuomba kuona au kurekebisha taarifa kupitia shule.</div>

      <p>This policy explains what {SITE.app} collects, why, who can see it and how it is protected. {SITE.app} is run by {SITE.school} (“the school”), which is responsible for the information in it. Most students are under 18, so the school handles their information on the basis of its duty to educate and assess them, and with care for parents and guardians.</p>

      <h2>1. What we collect</h2>
      <ul>
        <li><b>Account details:</b> name, username, index number, class and stream, role (student, teacher or admin), and your choices for language, theme and accessibility.</li>
        <li><b>Exam and practice records:</b> your answers, scores, grades, start and finish times, retakes or extra time, and practice sessions.</li>
        <li><b>Engagement records:</b> streaks, XP, level, badges and leaderboard position.</li>
        <li><b>Exam integrity information:</b> how many times the exam screen was left. This is information for teachers only and is never treated as proof of cheating.</li>
        <li><b>Security records:</b> logins, failed log-ins, password changes, and what staff did in the system (the audit log).</li>
        <li><b>Parent and guardian contact details:</b> name, relationship and mobile number, kept encrypted. They are used only to send a child’s login details and school notices, and are visible only to administrators, who see the number hidden unless they choose to show it. Every time one is shown is recorded.</li>
        <li><b>Optional notifications:</b> if you switch on push notifications, your browser gives us a notification address so results and reminders can reach you.</li>
      </ul>
      <p>We do <b>not</b> collect your location, contacts, photos (unless a teacher adds a question image), or payment details.</p>

      <h2>2. Why we use it</h2>
      <ul>
        <li>To run, time, mark and publish school exams fairly.</li>
        <li>To show students their results, review and progress.</li>
        <li>To help teachers see which topics need reteaching and which students need support.</li>
        <li>To keep the system secure and to investigate problems.</li>
        <li>To encourage regular practice through streaks and badges. Rewards never change marks.</li>
      </ul>

      <h2>3. Who can see it</h2>
      <ul>
        <li><b>You:</b> your own answers, results and progress only. Another student cannot open your result.</li>
        <li><b>Teachers:</b> results and analytics for the subjects and classes assigned to them, after results are published. During a live exam teachers see participation numbers only.</li>
        <li><b>Administrators:</b> everything needed to run the school’s exams and accounts. Only a Super Admin can permanently delete data.</li>
        <li><b>Other students:</b> the online counter shows a number, never names. The leaderboard shows only what the school has switched on.</li>
      </ul>
      <p>We do not sell your information, show advertising, or use third-party tracking or analytics. We share information outside the school only if the law requires it or an education authority properly asks for it.</p>

      <h2>4. What is stored on your device</h2>
      <p>To work properly the app keeps a few things in your browser: a login token, your display choices, answers waiting to sync if you go offline, and cached copies of the app’s own files so it opens quickly. Exam questions and results are always loaded fresh from the server and are not cached. Logging out removes the login token. You can clear the rest in your browser settings. There are no advertising or tracking cookies.</p>

      <h2>5. How long we keep it</h2>
      <p>Records are kept {SITE.retention}. “Deleting” a student archives the account, which can be restored. Permanent deletion is done by a Super Admin.</p>

      <h2>6. How we protect it</h2>
      <ul>
        <li>Passwords are stored scrambled (hashed), never in plain text, and staff cannot read them.</li>
        <li>Connections use HTTPS on the live site.</li>
        <li>Only one active login per account, and an account locks for a while after repeated wrong passwords.</li>
        <li>Access depends on role, and important staff actions are written to an audit log that cannot be edited.</li>
        <li>The database is backed up regularly and restore tests are carried out.</li>
        <li>Parents’ names and phone numbers are encrypted with a secret key kept apart from the database. A child’s first password is random, is sent to her parent by text message from a school phone, is erased from our system once sent, and must be replaced by the child at first login.</li>
      </ul>
      <p>No system is perfectly safe. Please keep your password private and log out on shared devices.</p>

      <h2>7. Your rights</h2>
      <p>You, or your parent or guardian, may ask the school to show you the information held about you, correct it if it is wrong, or delete it where the law and school record-keeping rules allow. Exam marks are generated automatically, so corrections are made by fixing the cause (for example voiding a faulty question) and not by editing one score. If you are unhappy with how your information is handled, tell the school first. You may also complain to the national personal data protection authority of Tanzania.</p>

      <h2>8. Changes</h2>
      <p>If this policy changes, the new version appears here with a new date.</p>

      <h2>9. Contact</h2>
      <p>{SITE.school}, {SITE.address}<br />E-mail: <a href={`mailto:${SITE.email}`}>{SITE.email}</a> · Phone: {SITE.phone}</p>
    </PublicPage>
  );
}
