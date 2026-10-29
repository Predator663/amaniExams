"use client";
import PublicPage from "@/components/PublicPage";
import { useSession } from "@/lib/session";
import { SITE } from "@/lib/site";

export default function Privacy() {
  const { t } = useSession();
  return (
    <PublicPage title={t("privacy_title")} updated>
      <div className="hint"><b>Muhtasari kwa Kiswahili.</b> Tunakusanya jina, namba ya mtihani, darasa, majibu na matokeo yako ili kuendesha mitihani ya shule. Hatuuzi taarifa zako, hatuna matangazo, na hatutumii wafuatiliaji wa nje. Wakati wa mtihani, simu yako hutuma eneo lake (GPS, Wi-Fi) ili shule ijue kama wanafunzi wawili wanakaa karibu zaidi ya mita 20; eneo hili hutumika wakati wa mtihani tu. Matokeo yako huonekana kwako, kwa walimu wa masomo yako na kwa utawala wa shule tu. Mzazi au mlezi anaweza kuomba kuona au kurekebisha taarifa kupitia shule.</div>

      <p>This policy explains what {SITE.app} collects, why, who can see it and how it is protected. {SITE.app} is run by {SITE.school} (“the school”), which is responsible for the information in it. Most students are under 18, so the school handles their information on the basis of its duty to educate and assess them, and with care for parents and guardians.</p>

      <h2>1. What we collect</h2>
      <ul>
        <li><b>Account details:</b> name, username, index number, class and stream, role (student, teacher or admin), and your choices for language, theme and accessibility.</li>
        <li><b>Exam and practice records:</b> your answers, scores, grades, start and finish times, retakes or extra time, and practice sessions.</li>
        <li><b>Engagement records:</b> streaks, XP, level, badges and leaderboard position.</li>
        <li><b>Exam integrity information:</b> how many times the exam screen was left. This is information for teachers only and is never treated as proof of cheating.</li>
        <li><b>Location during exams (see section 2A):</b> while an exam attempt is running, your phone sends its position and a few device status words. Nothing is collected before you start or after you submit.</li>
        <li><b>Your acceptance:</b> the date and the version of the Terms of use and this Privacy policy you accepted before each exam.</li>
        <li><b>Security records:</b> logins, failed log-ins, password changes, and what staff did in the system (the audit log).</li>
        <li><b>Parent and guardian contact details:</b> name, relationship and mobile number, kept encrypted. They are used only to send a child’s login details and school notices, and are visible only to administrators, who see the number hidden unless they choose to show it. Every time one is shown is recorded.</li>
        <li><b>Optional notifications:</b> if you switch on push notifications, your browser gives us a notification address so results and reminders can reach you.</li>
      </ul>
      <p>We do <b>not</b> collect your location outside an exam attempt, your contacts, photos (unless a teacher adds a question image), or payment details.</p>

      <h2>2. Why we use it</h2>
      <ul>
        <li>To run, time, mark and publish school exams fairly.</li>
        <li>To show students their results, review and progress.</li>
        <li>To help teachers see which topics need reteaching and which students need support.</li>
        <li>To keep the system secure and to investigate problems.</li>
        <li>To encourage regular practice through streaks and badges. Rewards never change marks.</li>
      </ul>

      <h2>2A. Location during exams (anti-cheating check)</h2>
      <p>Exams are written at home, so the school checks that students are not sitting together and sharing answers. To do this, from the moment you start an exam until you submit it, the app asks your phone or computer for its position and sends it to the school’s server about every 6 seconds.</p>
      <ul>
        <li><b>What is used:</b> the phone’s own location service, which combines GPS/GNSS satellites, nearby Wi-Fi and the mobile network to find where you are, and reports how accurate the position is. The app also reads the phone’s motion sensor, only to tell whether the phone is being moved, and a few status words: whether Location is allowed, whether Bluetooth is on, and what kind of network (Wi-Fi or mobile data) is being used. The app does <b>not</b> record your Wi-Fi network names or passwords, scan other people’s devices, or read the Bluetooth devices around you. The web browser does not allow this.</li>
        <li><b>What it is for:</b> to detect whether two or more students taking the same exam are sitting closer together than the distance the school has set (20 metres unless the school changes it), to see whether a student’s Location is switched off, and to check that the position and the device are genuine (see “Device and position checks” below). If the school has switched on locking, the exam of two students who are confirmed to be that close is locked and a message tells them to move apart; the exam timer keeps running, and an administrator unlocks it. The information is not used for anything else, and it is never sold, shared with advertisers or published.</li>
        <li><b>Device and position checks:</b> while an exam runs, the server also keeps (a) a random code that your browser made for itself, the kind of device it is (for example Android or Windows, taken from the browser’s own description) and the network address your connection comes from, so the school can see if your exam is suddenly sent from a different device, and (b) a few counters on how your position behaves from one report to the next, so it can notice a position that is not real GPS, for example one that never changes at all or jumps to another place. The code is not your phone number, IMEI or any hardware identifier. If one of these checks triggers, a short note is kept with the exam integrity records (the kind of check, the times, a short device code, the kind of device and the network address, never your whole device code). Like an alert, it is not proof: an administrator reviews it and may speak with you first, and marks are never changed automatically.</li>
        <li><b>Place names:</b> so an administrator can see roughly where a student is (for example the street, district and country), the school’s server turns a position into a place name by asking an address-lookup service (by default OpenStreetMap’s Nominatim, or a service run by the school). Only the position, rounded to about 10 metres, is sent. No name, index number, exam or other detail about you is sent, and this is done only for the administrator’s screen. The place name is approximate because the position itself is approximate. The school can switch this off.</li>
        <li><b>Who sees it:</b> school administrators only, in the Live monitor → Anti-cheat tab, with your name. Teachers and other students cannot see it. When two students are close, administrators get an alert.</li>
        <li><b>Related students:</b> if two students are twins, live in the same house or sit in the same room, an administrator can record that, so the system does not raise an alert or lock them when they are close. The record (the two names and the kind of relation, for example “twins”) can be seen by administrators only, is kept until an administrator removes it, and is used for nothing else.</li>
        <li><b>Messages from the school:</b> an administrator can send a message to your account, for example to ask you to move away from another student during an exam. It shows at the top of your screen until you close it, and then stays in your Messages tab until an administrator deletes it. Only you and the administrators can read it.</li>
        <li><b>An alert is not proof:</b> a position can be inaccurate, and brothers, sisters and neighbours can live close together. An administrator looks at the alert and decides what, if anything, to do, and may speak with you and your parent or guardian first. Marks are never changed automatically because of an alert.</li>
        <li><b>You must keep Location, Wi-Fi and Bluetooth on</b> during the exam, and allow Location for this app. If Location is switched off, the questions are hidden until it is back on, and the exam timer keeps running. Tell your teacher beforehand if your phone cannot do this.</li>
        <li><b>How long it is kept:</b> only your latest position is stored, and each new position replaces the last, so the system does not keep a trail of where you have been. Stored positions of finished exams are deleted within 24 hours. If an alert was raised, a record of it (the two names, the closest distance and time, and the two positions at that moment) is kept with the school’s exam integrity records {SITE.retention}.</li>
        <li><b>Your agreement:</b> you must accept this policy and the Terms of use before you begin each exam. Because most students are under 18, we ask your parent or guardian to be aware of this check. If you or your parent or guardian do not accept it, speak to the school about another way of sitting the exam.</li>
      </ul>

      <h2>3. Who can see it</h2>
      <ul>
        <li><b>You:</b> your own answers, results and progress only. Another student cannot open your result.</li>
        <li><b>Teachers:</b> results and analytics for the subjects and classes assigned to them, after results are published. During a live exam teachers see participation numbers only, never your location.</li>
        <li><b>Administrators:</b> everything needed to run the school’s exams and accounts, including your position during an exam and proximity alerts (section 2A). Reviewing an alert is recorded in the audit log. Only a Super Admin can permanently delete data.</li>
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
        <li>Connections use HTTPS on the live site. Student positions are drawn on a plain plan by the school’s own system, not on a map service. The only thing that can leave the school’s server is a rounded position sent to the address-lookup service described in section 2A, without any name.</li>
        <li>Only one active login per account, and an account locks for a while after repeated wrong passwords.</li>
        <li>Access depends on role, and important staff actions are written to an audit log that cannot be edited.</li>
        <li>The database is backed up regularly and restore tests are carried out.</li>
        <li>Parents’ names and phone numbers are encrypted with a secret key kept apart from the database. A child’s first password is random, is sent to her parent by text message from a school phone, is erased from our system once sent, and must be replaced by the child at first login.</li>
      </ul>
      <p>No system is perfectly safe. Please keep your password private and log out on shared devices.</p>

      <h2>7. Your rights</h2>
      <p>You, or your parent or guardian, may ask the school to show you the information held about you, correct it if it is wrong, or delete it where the law and school record-keeping rules allow. Exam marks are generated automatically, so corrections are made by fixing the cause (for example voiding a faulty question) and not by editing one score. If you are unhappy with how your information is handled, tell the school first. You may also complain to the national personal data protection authority of Tanzania.</p>

      <h2>8. Changes</h2>
      <p>If this policy changes, the new version appears here with a new date. Each exam asks you to accept the current version.</p>

      <h2>9. Contact</h2>
      <p>{SITE.school}, {SITE.address}<br />E-mail: <a href={`mailto:${SITE.email}`}>{SITE.email}</a> · Phone: {SITE.phone}</p>
    </PublicPage>
  );
}
