package tz.ac.amani.smssender

import android.content.Context

/** Settings, the list of messages already sent (so a message is never sent twice), and the on-screen log. */
object Store {
    private const val FILE = "sender"

    fun serverUrl(c: Context): String = c.getSharedPreferences(FILE, Context.MODE_PRIVATE).getString("server", "") ?: ""
    fun token(c: Context): String = c.getSharedPreferences(FILE, Context.MODE_PRIVATE).getString("token", "") ?: ""

    fun save(c: Context, server: String, token: String) {
        c.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit()
            .putString("server", server.trim().trimEnd('/'))
            .putString("token", token.trim())
            .apply()
    }

    @Synchronized
    fun wasSent(c: Context, id: Long): Boolean = sentIds(c).contains(id)

    @Synchronized
    fun markSent(c: Context, id: Long) {
        val ids = sentIds(c).toMutableList()
        if (!ids.contains(id)) ids.add(id)
        val keep = ids.takeLast(500)
        c.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit().putString("sent", keep.joinToString(",")).apply()
    }

    private fun sentIds(c: Context): List<Long> =
        (c.getSharedPreferences(FILE, Context.MODE_PRIVATE).getString("sent", "") ?: "")
            .split(",").mapNotNull { it.toLongOrNull() }
}

object AppLog {
    private val lines = ArrayDeque<String>()
    private val clock = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.US)

    @Synchronized
    fun add(msg: String) {
        lines.addLast("${clock.format(java.util.Date())}  $msg")
        while (lines.size > 80) lines.removeFirst()
    }

    @Synchronized
    fun text(): String = lines.reversed().joinToString("\n")
}
