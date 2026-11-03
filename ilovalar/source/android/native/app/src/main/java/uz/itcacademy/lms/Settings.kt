package uz.itcacademy.lms

import android.content.Context
import android.content.SharedPreferences
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** Ilova sozlamalari: o'zgarsa interfeys darhol yangilanadi. */
object Settings {
    private lateinit var p: SharedPreferences

    var theme by mutableStateOf("dark")
    var accent by mutableStateOf("violet")
    var lang by mutableStateOf("uz")
    var motion by mutableStateOf(true)
    var sound by mutableStateOf(true)
    var coinToast by mutableStateOf(true)

    fun init(ctx: Context) {
        p = ctx.getSharedPreferences("itc_settings", Context.MODE_PRIVATE)
        theme = p.getString("theme", "dark") ?: "dark"
        accent = p.getString("accent", "violet") ?: "violet"
        lang = p.getString("lang", "uz") ?: "uz"
        motion = p.getBoolean("motion", true)
        sound = p.getBoolean("sound", true)
        coinToast = p.getBoolean("coinToast", true)
    }

    fun update(block: Settings.() -> Unit) {
        block()
        p.edit()
            .putString("theme", theme).putString("accent", accent).putString("lang", lang)
            .putBoolean("motion", motion).putBoolean("sound", sound).putBoolean("coinToast", coinToast)
            .apply()
    }

    var lastLogin: String
        get() = p.getString("lastLogin", "") ?: ""
        set(v) = p.edit().putString("lastLogin", v).apply()

    /** "Davom ettirish" ro'yxati: faqat shu qurilmada saqlanadi, Windows ilovasidagidek. */
    fun visited(courseId: Int): Set<Int> =
        p.getStringSet("visited.$courseId", emptySet()).orEmpty().mapNotNull { it.toIntOrNull() }.toSet()

    fun markVisited(courseId: Int, lessonId: Int) {
        p.edit().putStringSet("visited.$courseId", (visited(courseId) + lessonId).map { it.toString() }.toSet()).apply()
    }

    fun recent(): List<JSONObject> {
        val arr = runCatching { org.json.JSONArray(p.getString("recent", "[]")) }.getOrNull() ?: return emptyList()
        return (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }
    }

    fun pushRecent(id: Int, title: String, type: String, courseId: Int, course: String) {
        val item = JSONObject().put("id", id).put("title", title).put("type", type)
            .put("courseId", courseId).put("course", course).put("at", System.currentTimeMillis())
        val list = listOf(item) + recent().filter { it.optInt("id") != id }
        p.edit().putString("recent", org.json.JSONArray(list.take(12)).toString()).apply()
    }

    /** Boshlangan testning imzolangan urinishi va javoblari: ilova yopilsa ham davom etadi. */
    fun testState(lessonId: Int): JSONObject? = p.getString("test.$lessonId", null)?.let { runCatching { JSONObject(it) }.getOrNull() }
    fun saveTestState(lessonId: Int, state: JSONObject?) {
        p.edit().apply { if (state == null) remove("test.$lessonId") else putString("test.$lessonId", state.toString()) }.apply()
    }

    fun clearHistory() {
        val e = p.edit().remove("recent")
        p.all.keys.filter { it.startsWith("visited.") || it.startsWith("test.") }.forEach { e.remove(it) }
        e.apply()
    }
}

/**
 * Tarjima. Interfeys o'zbekcha yoziladi, ru/en Windows ilovasi bilan bitta lug'atdan olinadi.
 * Tarjimasi yo'q matn o'zbekcha qoladi.
 */
object I18n {
    private var exact: Map<String, String> = emptyMap()
    private var patterns: List<Pair<Regex, Pair<String, List<String>>>> = emptyList()
    private var loaded by mutableStateOf("uz")
    private val memo = HashMap<String, String>()

    val LANGS = listOf("uz" to "O'zbekça", "ru" to "Русский", "en" to "English")
    val COUNTRY = mapOf("uz" to "Özbekiston", "ru" to "Россия", "en" to "United Kingdom")

    suspend fun load(ctx: Context, lang: String) = withContext(Dispatchers.IO) {
        memo.clear()
        if (lang == "uz") {
            exact = emptyMap(); patterns = emptyList(); withContext(Dispatchers.Main) { loaded = lang }
            return@withContext
        }
        val text = runCatching { ctx.assets.open("$lang.json").bufferedReader().use { it.readText() } }.getOrNull()
        if (text == null) {
            exact = emptyMap(); patterns = emptyList(); withContext(Dispatchers.Main) { loaded = lang }
            return@withContext
        }
        val o = JSONObject(text)
        val t = o.getJSONObject("t")
        val map = HashMap<String, String>(t.length() * 2)
        t.keys().forEach { k -> map[k] = t.getString(k) }
        val arr = o.optJSONArray("p")
        val pats = ArrayList<Pair<Regex, Pair<String, List<String>>>>()
        if (arr != null) for (i in 0 until arr.length()) {
            val pair = arr.getJSONArray(i)
            val src = pair.getString(0)
            val slots = Regex("\\{\\d+\\}").findAll(src).map { it.value }.toList()
            val re = src.split(Regex("\\{\\d+\\}")).joinToString("(.+?)") { Regex.escape(it) }
            pats += Regex("^$re$") to (pair.getString(1) to slots)
        }
        pats.sortByDescending { it.first.pattern.length }
        exact = map
        patterns = pats
        withContext(Dispatchers.Main) { loaded = lang }
    }

    /** Composable ichida o'qilganda til almashsa matn ham yangilanadi. */
    fun t(value: String): String {
        val cur = loaded
        if (cur == "uz" || value.isBlank()) return value
        memo[value]?.let { return it }
        val clean = value.trim()
        val found = exact[clean] ?: fromPattern(clean) ?: value
        memo[value] = found
        return found
    }

    private fun fromPattern(text: String): String? {
        if (text.length > 400) return null
        for ((re, target) in patterns) {
            val m = re.find(text) ?: continue
            var out = target.first
            target.second.forEachIndexed { i, slot ->
                val v = m.groupValues[i + 1]
                out = out.replace(slot, exact[v] ?: v)
            }
            return out
        }
        return null
    }
}

fun t(s: String) = I18n.t(s)
