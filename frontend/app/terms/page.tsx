"use client";
import PublicPage from "@/components/PublicPage";
import { useSession } from "@/lib/session";
import { SITE } from "@/lib/site";

export default function Terms() {
  const { t } = useSession();
  return (
    <PublicPage title={t("terms_title")} updated>
      <div className="hint"><b>Muhtasari kwa Kiswahili.</b> Tumia akaunti yako mwenyewe, usimpe mtu nenosiri lako, na ufanye mtihani kwa uaminifu. Usijaribu kuingia kwenye akaunti za wengine. Wakati wa mtihani lazima uwashe Eneo (GPS), Wi-Fi na Bluetooth, na ukubali masharti na sera ya faragha kabla ya kuanza. Wanafunzi wawili wakikaa chini ya mita 20 kutoka kwa kila mmoja, utawala hupata taarifa. Shule inaweza kusimamisha akaunti inayotumiwa vibaya. Kwa kutumia mfumo huu unakubali masharti haya.</div>

      <p>These terms apply when you use {SITE.app}, the online examination system of {SITE.school}. By logging in you agree to them. If you are under 18, your parent or guardian’s agreement with the school’s rules also applies.</p>

      <h2>1. Your account</h2>
      <ul>
        <li>Your account is for you alone. Never share your password or let anyone else sit an exam as you.</li>
        <li>Change the first password you were given, choose a strong one, and log out on shared devices.</li>
        <li>Tell a teacher or the administrator at once if you think someone else has used your account.</li>
      </ul>

      <h2>2. Taking exams honestly</h2>
      <ul>
        <li>Do your own work. Do not use notes, other people, other devices or messaging during an exam unless the exam rules say you may.</li>
        <li>Do not try to change the clock, reload to gain time, copy questions, or share questions or answers.</li>
        <li>The system records when the exam screen is left. This is information for teachers and is not proof of cheating, but cheating is a school discipline matter.</li>
        <li>Sit apart from other students writing the same exam. Do not sit within 20 metres of another student taking the exam, and do not take the exam in a group.</li>
        <li>Do not try to reach other people’s data, break the system, overload it, or test its security without written permission from the school.</li>
      </ul>

      <h2>2A. Phone settings and location checks during exams</h2>
      <ul>
        <li><b>Accept before you begin.</b> Before every exam you must tick that you accept these Terms of use and the <a href="/privacy/">Privacy policy</a>. Without it the exam cannot be started.</li>
        <li><b>Turn on Location (GPS), Wi-Fi and Bluetooth</b> when the exam window opens, allow Location for this app, and keep all three on until you submit. The exam cannot be started without Location, and if Location is switched off during the exam the questions are hidden until it is on again. The timer keeps running meanwhile.</li>
        <li><b>What is checked.</b> While you write, your phone’s position and motion are sent to the school, so administrators can see whether two or more students are sitting closer together than the distance the school has set (20 metres unless changed). If the school has switched on locking, your exam is locked while you sit that close to another student: a message tells you to move apart, the timer keeps running, and an administrator unlocks it. Details, who sees them and how long they are kept are in section 2A of the Privacy policy.</li>
        <li><b>Alerts are not a verdict.</b> A close position can have an innocent reason, such as a sister in the same house, and positions are not always exact. An administrator reviews every alert, and you will be given a chance to explain before any action is taken.</li>
        <li><b>Do not tamper.</b> Do not use fake-location apps, airplane mode, a second device or any other trick to hide or change where you are. Do not log in again on another phone or computer while you are writing, and do not share your password. The school checks for a change of device and for positions that are not real GPS. This counts as cheating.</li>
        <li><b>If your phone cannot do this,</b> or you have a good reason not to share your location, tell your teacher before the exam so the school can arrange another way.</li>
      </ul>

      <h2>3. Marking and results</h2>
      <p>Answers are marked automatically. Nobody can change one student’s score. If a question is found to be faulty, the school may void it and all results are recalculated. Results appear only at the published time. In special cases, such as a power cut, an administrator may grant extra time or a retake, and the reason is recorded.</p>

      <h2>4. Availability</h2>
      <p>We work to keep the system running during exams, and the app is designed to cope with short connection losses. GPS can be slow or inaccurate indoors; if your position cannot be found, move near a window or outside. We cannot promise it will always be available or error-free, for example if your phone, network or electricity fails. If something goes wrong during an exam, tell your teacher straight away.</p>

      <h2>5. Content</h2>
      <p>Questions, papers, explanations and results belong to {SITE.school} and its teachers. You may use them for your own study but not copy, publish or sell them. Your own answers remain yours, and the school may use them to mark, report and improve teaching.</p>

      <h2>6. Misuse</h2>
      <p>The school may suspend or close an account, void an exam attempt, or apply its normal discipline rules if these terms are broken. Serious misuse may be reported to the proper authorities.</p>

      <h2>7. Liability</h2>
      <p>The system is provided for school use “as is”. To the extent the law allows, the school is not responsible for losses caused by things outside its control, such as device or network failure. Nothing here limits any right you have under Tanzanian law.</p>

      <h2>8. Changes and law</h2>
      <p>The school may update these terms and will show the new date here. These terms are governed by the laws of the United Republic of Tanzania. Your personal information is handled as described in the <a href="/privacy/">privacy policy</a>.</p>

      <h2>9. Contact</h2>
      <p>{SITE.school}, {SITE.address}<br />E-mail: <a href={`mailto:${SITE.email}`}>{SITE.email}</a> · Phone: {SITE.phone}</p>
    </PublicPage>
  );
}
