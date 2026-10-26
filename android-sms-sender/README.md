# Amani SMS Sender (Android)

A small app for the school phone. It asks the Amani Exams website for waiting messages (parents' login details) and
sends each one as a normal SMS from the phone's SIM card, slowly, then tells the website whether it worked.

> **Not yet compiled or tested on a phone.** The website side is tested (see `guardians/tests.py`). This app was written
> carefully but could not be built in the place where it was written. Build it, try it with ONE message to your own
> number first, and send me any error you see in Android Studio.

## Build
1. Install **Android Studio**, choose *Open*, and select this folder (`android-sms-sender`). Let it finish "Gradle sync".
2. *Build > Build Bundle(s) / APK(s) > Build APK(s)*. The file is `app/build/outputs/apk/debug/app-debug.apk`.
3. Copy the APK to the school phone, open it, allow "install unknown apps" for your file manager, install.

## Set up the phone (once)
1. Use a phone with the SIM that has an **SMS bundle**. On a dual-SIM phone, set that SIM as the default for SMS
   (Settings > SIM / Mobile network > SMS).
2. On the website: **Parents > Phone**: write the school web address, press *Create pairing code*, copy the code.
3. In the app: type the **server address** (the website address, for example `https://amani-exams.co.tz`) and the
   **pairing code**, press *Save and check the connection*. The log should say "Connected".
4. Press *Battery settings* and allow the app to run in the background, so Android does not stop it.
5. Press *Start sending* and allow the SMS permission.

## Sending
On the website: **Parents > Send > Check who will get a message > Queue**. The phone sends them one by one
(about 8 seconds apart, and a 3-minute rest after every 30; change this in Parents > Phone). The website shows
queued, sent, delivered or failed for every parent.

## Good to know
- Keep the phone **charged, with a signal, and the app running** (a notification shows while it works).
- If the phone is switched off, nothing is lost: messages simply wait in the queue.
- A message is never sent twice: the app remembers what it sent.
- Testing on your own Wi-Fi over plain `http://` works (the manifest allows it). For real use put the website behind
  **https** and set `usesCleartextTraffic="false"` in `AndroidManifest.xml`.
- Anyone who has the pairing code can send SMS as the school. Remove a lost phone with *Parents > Phone > Remove*.
