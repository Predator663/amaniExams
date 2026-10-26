package tz.ac.amani.smssender

import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.net.Uri
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.telephony.SmsManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import java.io.IOException
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import kotlin.random.Random

/**
 * Asks the website for waiting messages and sends each one as a normal SMS from this phone's SIM card,
 * slowly (a pause between messages, and a longer rest every so often), then tells the website what happened.
 */
class SenderService : Service() {

    companion object {
        const val ACTION_STOP = "tz.ac.amani.smssender.STOP"
        private const val ACTION_SENT = "tz.ac.amani.smssender.SENT"
        private const val ACTION_DELIVERED = "tz.ac.amani.smssender.DELIVERED"
        private const val EXTRA_JOB = "job"
        private const val CHANNEL = "sender"
        private val NUMBER = Regex("^\\+255[67]\\d{8}$")

        @Volatile
        var running = false
    }

    private class JobState(var sentLeft: Int, var deliveredLeft: Int, var failure: String? = null)

    private val states = ConcurrentHashMap<Long, JobState>()
    private val net = Executors.newSingleThreadExecutor()
    private var worker: Thread? = null
    private var wake: PowerManager.WakeLock? = null
    private lateinit var api: Api
    private var receiverOn = false

    /** Android tells us here, part by part, whether the SIM sent the message and whether the phone received it. */
    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(ctx: Context, intent: Intent) {
            val id = intent.getLongExtra(EXTRA_JOB, -1L)
            val st = states[id] ?: return
            val ok = resultCode == Activity.RESULT_OK
            if (intent.action == ACTION_SENT) {
                if (!ok && st.failure == null) st.failure = reason(resultCode)
                st.sentLeft -= 1
                if (st.sentLeft == 0) {
                    val failure = st.failure
                    if (failure != null) {
                        AppLog.add("FAILED (job $id): $failure")
                        report(id, "failed", failure)
                        states.remove(id)
                    } else {
                        Store.markSent(this@SenderService, id)
                        AppLog.add("Sent (job $id)")
                        report(id, "sent")
                    }
                }
            } else if (intent.action == ACTION_DELIVERED && ok) {
                st.deliveredLeft -= 1
                if (st.deliveredLeft == 0 && st.failure == null) {
                    AppLog.add("Delivered (job $id)")
                    report(id, "delivered")
                    states.remove(id)
                }
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopWork()
            return START_NOT_STICKY
        }
        if (running) return START_STICKY
        val server = Store.serverUrl(this)
        val token = Store.token(this)
        if (server.isEmpty() || token.isEmpty()) {
            AppLog.add("Enter the server address and the pairing code first.")
            stopSelf()
            return START_NOT_STICKY
        }
        api = Api(server, token)
        startAsForeground()
        val filter = IntentFilter().apply {
            addAction(ACTION_SENT)
            addAction(ACTION_DELIVERED)
            addDataScheme("amani") // our PendingIntents carry an amani:// address so every message part is unique
        }
        ContextCompat.registerReceiver(this, receiver, filter, ContextCompat.RECEIVER_NOT_EXPORTED)
        receiverOn = true
        wake = (getSystemService(Context.POWER_SERVICE) as PowerManager)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "amani:sender").apply { acquire(12 * 60 * 60 * 1000L) }
        running = true
        worker = Thread { loop() }.also { it.start() }
        return START_STICKY
    }

    private fun loop() {
        var sinceRest = 0
        AppLog.add("Started. Asking the website for messages...")
        while (running) {
            try {
                val (jobs, pacing) = api.pull(10)
                if (jobs.isEmpty()) {
                    nap(10)
                    continue
                }
                AppLog.add("${jobs.size} message(s) to send")
                for (job in jobs) {
                    if (!running) break
                    if (Store.wasSent(this, job.id)) { // the website asked again because it never heard back: do not text twice
                        report(job.id, "sent")
                        continue
                    }
                    sendOne(job)
                    sinceRest++
                    if (pacing.pauseEvery > 0 && sinceRest >= pacing.pauseEvery) {
                        AppLog.add("Resting ${pacing.pauseSeconds} s so the network does not block the SIM")
                        nap(pacing.pauseSeconds)
                        sinceRest = 0
                    } else {
                        nap(pacing.secondsBetween + Random.nextInt(0, 3))
                    }
                }
            } catch (e: AuthException) {
                AppLog.add(e.message ?: "The pairing code was rejected.")
                break
            } catch (e: IOException) {
                AppLog.add("No connection (${e.message}). Trying again in 30 s.")
                nap(30)
            } catch (e: Exception) {
                AppLog.add("Problem: ${e.javaClass.simpleName} ${e.message}")
                nap(30)
            }
        }
        stopWork()
    }

    private fun sendOne(job: Job) {
        if (!NUMBER.matches(job.to)) {
            AppLog.add("Skipped a bad phone number")
            report(job.id, "failed", "Bad phone number")
            return
        }
        try {
            val sms = smsManager()
            val parts = sms.divideMessage(job.body)
            val sent = ArrayList<PendingIntent>()
            val delivered = ArrayList<PendingIntent>()
            for (i in parts.indices) {
                sent.add(pending(ACTION_SENT, job.id, i))
                delivered.add(pending(ACTION_DELIVERED, job.id, i))
            }
            states[job.id] = JobState(parts.size, parts.size)
            sms.sendMultipartTextMessage(job.to, null, parts, sent, delivered)
            AppLog.add("Sending to ${job.to.take(4)}*****${job.to.takeLast(3)} (${parts.size} part(s))")
        } catch (e: Exception) {
            val why = "${e.javaClass.simpleName}: ${e.message ?: ""}"
            AppLog.add("FAILED: $why")
            report(job.id, "failed", why)
        }
    }

    private fun pending(action: String, id: Long, part: Int): PendingIntent {
        val intent = Intent(action)
            .setPackage(packageName)
            .setData(Uri.parse("amani://sms/${action.substringAfterLast('.')}/$id/$part"))
            .putExtra(EXTRA_JOB, id)
        return PendingIntent.getBroadcast(this, 0, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }

    private fun smsManager(): SmsManager =
        if (Build.VERSION.SDK_INT >= 31) getSystemService(SmsManager::class.java)
        else @Suppress("DEPRECATION") SmsManager.getDefault()

    private fun reason(code: Int): String = when (code) {
        SmsManager.RESULT_ERROR_GENERIC_FAILURE -> "Could not send (check airtime or the SMS bundle)"
        SmsManager.RESULT_ERROR_NO_SERVICE -> "No network signal"
        SmsManager.RESULT_ERROR_NULL_PDU -> "The message was not valid"
        SmsManager.RESULT_ERROR_RADIO_OFF -> "Airplane mode is on"
        else -> "Android error $code"
    }

    /** Tell the website. Runs off the main thread; if it fails the website simply asks for the message again later. */
    private fun report(id: Long, status: String, error: String = "") {
        net.execute {
            try {
                api.report(id, status, error)
            } catch (e: Exception) {
                AppLog.add("Could not tell the website ($status): ${e.message}")
            }
        }
    }

    private fun nap(seconds: Int) {
        var left = seconds * 1000L
        while (running && left > 0) {
            Thread.sleep(500)
            left -= 500
        }
    }

    private fun startAsForeground() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, "Sending messages", NotificationManager.IMPORTANCE_LOW))
        val stop = PendingIntent.getService(
            this, 1, Intent(this, SenderService::class.java).setAction(ACTION_STOP), PendingIntent.FLAG_IMMUTABLE
        )
        val open = PendingIntent.getActivity(this, 2, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val n: Notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_notify_chat)
            .setContentTitle("Amani SMS Sender is running")
            .setContentText("Sending parents' login messages")
            .setContentIntent(open)
            .addAction(0, "Stop", stop)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        else startForeground(1, n)
    }

    private fun stopWork() {
        running = false
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        running = false
        if (receiverOn) {
            try { unregisterReceiver(receiver) } catch (ignored: Exception) { }
            receiverOn = false
        }
        try { wake?.takeIf { it.isHeld }?.release() } catch (ignored: Exception) { }
        AppLog.add("Stopped.")
        super.onDestroy()
    }
}
