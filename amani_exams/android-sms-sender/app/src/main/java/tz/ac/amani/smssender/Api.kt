package tz.ac.amani.smssender

import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

class AuthException : IOException("The pairing code was rejected. Create a new one on the website (Parents, then Phone).")

data class Job(val id: Long, val to: String, val body: String)
data class Pacing(val secondsBetween: Int, val pauseEvery: Int, val pauseSeconds: Int)

/** The three calls the website offers to the phone (see guardians/views.py). */
class Api(private val server: String, private val token: String) {

    fun ping(): String {
        val j = JSONObject(call("GET", "/api/sms/ping/", null))
        return "Connected as \"${j.optString("name")}\". ${j.optInt("waiting")} message(s) waiting."
    }

    fun pull(limit: Int): Pair<List<Job>, Pacing> {
        val j = JSONObject(call("GET", "/api/sms/pull/?limit=$limit", null))
        val arr = j.getJSONArray("jobs")
        val jobs = (0 until arr.length()).map {
            val o = arr.getJSONObject(it)
            Job(o.getLong("id"), o.getString("to"), o.getString("body"))
        }
        val c = j.getJSONObject("config")
        return jobs to Pacing(c.optInt("seconds_between", 8), c.optInt("pause_every", 30), c.optInt("pause_seconds", 180))
    }

    fun report(id: Long, status: String, error: String = "") {
        val body = JSONObject().put("id", id).put("status", status).put("error", error).toString()
        call("POST", "/api/sms/report/", body)
    }

    private fun call(method: String, path: String, body: String?): String {
        val conn = (URL(server + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 20_000
            readTimeout = 30_000
            setRequestProperty("X-Device-Token", token)
            setRequestProperty("Accept", "application/json")
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                outputStream.use { it.write(body.toByteArray()) }
            }
        }
        try {
            val code = conn.responseCode
            if (code == 401) throw AuthException()
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() } ?: ""
            if (code !in 200..299) throw IOException("Server answered $code")
            return text
        } finally {
            conn.disconnect()
        }
    }
}
