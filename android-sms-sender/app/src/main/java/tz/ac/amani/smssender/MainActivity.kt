package tz.ac.amani.smssender

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.InputType
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.content.ContextCompat

/** One simple screen: server address, pairing code, Start / Stop, and a log. */
class MainActivity : Activity() {
    private lateinit var server: EditText
    private lateinit var token: EditText
    private lateinit var status: TextView
    private lateinit var log: TextView
    private lateinit var toggle: Button
    private val ui = Handler(Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() {
            log.text = AppLog.text()
            val on = SenderService.running
            toggle.text = if (on) "Stop sending" else "Start sending"
            status.text = if (on) "● Running: asking the website for messages" else "○ Stopped"
            ui.postDelayed(this, 1000)
        }
    }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun text(s: String, sp: Float, bold: Boolean = false) = TextView(this).apply {
        text = s
        textSize = sp
        if (bold) setTypeface(typeface, Typeface.BOLD)
        setPadding(0, dp(6), 0, dp(6))
    }

    private fun button(label: String, onClick: () -> Unit) = Button(this).apply {
        text = label
        isAllCaps = false
        setOnClickListener { onClick() }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(24), dp(18), dp(24))
        }
        col.addView(text("Amani SMS Sender", 24f, true))
        col.addView(text("Sends parents' login messages from this phone's SIM card. Keep this phone charged, with airtime or an SMS bundle, and a signal.", 14f))

        server = EditText(this).apply {
            hint = "Server address, e.g. https://amani-exams.co.tz"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setText(Store.serverUrl(this@MainActivity))
        }
        token = EditText(this).apply {
            hint = "Pairing code (from the website: Parents > Phone)"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            setText(Store.token(this@MainActivity))
        }
        col.addView(server)
        col.addView(token)
        col.addView(button("Save and check the connection") { saveAndPing() })

        status = text("", 16f, true)
        col.addView(status)
        toggle = button("Start sending") { if (SenderService.running) stopSending() else start() }
        col.addView(toggle)
        col.addView(button("Battery settings (allow this app to run in the background)") {
            startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        })

        col.addView(text("Log", 16f, true))
        log = TextView(this).apply {
            typeface = Typeface.MONOSPACE
            textSize = 12f
        }
        col.addView(log, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        setContentView(ScrollView(this).apply { addView(col) })
    }

    override fun onResume() {
        super.onResume()
        ui.post(tick)
    }

    override fun onPause() {
        ui.removeCallbacks(tick)
        super.onPause()
    }

    private fun saveAndPing() {
        Store.save(this, server.text.toString(), token.text.toString())
        val s = Store.serverUrl(this)
        val t = Store.token(this)
        Thread {
            try {
                AppLog.add(Api(s, t).ping())
            } catch (e: Exception) {
                AppLog.add("Connection failed: ${e.message}")
            }
        }.start()
    }

    private fun start() {
        Store.save(this, server.text.toString(), token.text.toString())
        val need = ArrayList<String>()
        if (checkSelfPermission(Manifest.permission.SEND_SMS) != PackageManager.PERMISSION_GRANTED) need.add(Manifest.permission.SEND_SMS)
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            need.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        if (need.isNotEmpty()) requestPermissions(need.toTypedArray(), 1) else launch()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (checkSelfPermission(Manifest.permission.SEND_SMS) == PackageManager.PERMISSION_GRANTED) launch()
        else AppLog.add("Permission to send SMS was refused. Allow it in the phone's app settings.")
    }

    private fun launch() = ContextCompat.startForegroundService(this, Intent(this, SenderService::class.java))

    private fun stopSending() {
        startService(Intent(this, SenderService::class.java).setAction(SenderService.ACTION_STOP))
    }
}
