package uz.itcacademy.parent

import android.content.Context
import android.content.SharedPreferences
import android.net.Uri
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

class ApiError(val status: Int, val data: JSONObject?) : Exception(messageFor(status, data)) {
    val code: String? get() = data?.optString("code")?.takeIf { it.isNotEmpty() }
}

private fun messageFor(status: Int, data: JSONObject?): String {
    if (status == 0) return "Internet aloqasi yöq yoki server javob bermayapti"
    data?.optString("error")?.takeIf { it.isNotEmpty() }?.let { return it }
    return when {
        status == 401 -> "Sessiya tugadi. Qaytadan kiring"
        status == 403 -> "Bu amal uçun ruxsat yöq"
        status == 404 -> "Topilmadi"
        status == 429 -> "Juda köp sörov. Birozdan keyin urinib köring"
        status >= 500 -> "Serverda xatolik. Keyinroq urinib köring"
        else -> "Kutilmagan xatolik"
    }
}

/** Shifrlangan xotira: token va PIN xeshi. Android Keystore kaliti bilan AES-256. */
object Secure {
    lateinit var prefs: SharedPreferences
        private set

    val ready: Boolean get() = ::prefs.isInitialized

    fun init(ctx: Context) {
        if (ready) return
        val key = MasterKey.Builder(ctx).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
        prefs = EncryptedSharedPreferences.create(
            ctx, "itcp_secure", key,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }
}

/** itc-academy.uz ota-ona API mijozi. Token faqat o'z saytimizga yuboriladi. */
object Api {
    val SITE: String = BuildConfig.SITE
    private val siteHost: String = Uri.parse(SITE).host.orEmpty()
    private const val BASE = "/api/v1/parent-app/"
    private const val USER_AGENT = "ITC-Ota-Ona-Android/${BuildConfig.VERSION_NAME} (Android; Mobile)"
    private val JSON = "application/json".toMediaType()
    private const val FRESH_MS = 30_000L

    private val cache = ConcurrentHashMap<String, Pair<Long, Any>>()
    var onUnauthorized: (() -> Unit)? = null

    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .followRedirects(false)
        .addInterceptor(Interceptor { chain ->
            val b = chain.request().newBuilder().header("User-Agent", USER_AGENT)
            val t = token
            if (t != null && chain.request().url.host == siteHost) b.header("Authorization", "Parent $t")
            chain.proceed(b.build())
        })
        .build()

    var token: String?
        get() = if (Secure.ready) Secure.prefs.getString("token", null) else null
        set(v) {
            Secure.prefs.edit().apply { if (v == null) remove("token") else putString("token", v) }.apply()
        }

    fun clearCache() = cache.clear()

    private fun url(path: String, params: Map<String, Any?>?): String {
        val b = Uri.parse(SITE + BASE + path.trimStart('/')).buildUpon()
        params?.forEach { (k, v) -> if (v != null && v.toString().isNotEmpty()) b.appendQueryParameter(k, v.toString()) }
        return b.build().toString()
    }

    private suspend fun call(method: String, url: String, body: JSONObject?): JSONObject = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(url).header("Accept", "application/json")
        if (method == "GET") req.get() else req.method(method, (body ?: JSONObject()).toString().toRequestBody(JSON))
        try {
            client.newCall(req.build()).execute().use { r ->
                val text = r.body?.string().orEmpty()
                val parsed = runCatching { JSONObject(text) }.getOrNull()
                if (r.isSuccessful) return@withContext parsed ?: JSONObject()
                if (r.code == 401 && token != null) {
                    token = null
                    withContext(Dispatchers.Main) { onUnauthorized?.invoke() }
                }
                throw ApiError(r.code, parsed)
            }
        } catch (e: IOException) {
            throw ApiError(0, null)
        }
    }

    suspend fun get(path: String, params: Map<String, Any?>? = null, fresh: Boolean = false): JSONObject {
        val u = url(path, params)
        if (!fresh) cache[u]?.let { (t, d) -> if (System.currentTimeMillis() - t < FRESH_MS) return d as JSONObject }
        return call("GET", u, null).also { cache[u] = System.currentTimeMillis() to it }
    }

    suspend fun post(path: String, body: JSONObject = JSONObject()): JSONObject =
        try { call("POST", url(path, null), body) } finally { clearCache() }

    suspend fun patch(path: String, body: JSONObject): JSONObject =
        try { call("PATCH", url(path, null), body) } finally { clearCache() }

    /** Sayt rasmi uchun to'liq manzil. Faqat o'z saytimizning /media va /static yo'llari. */
    fun media(raw: String?): String? {
        if (raw.isNullOrBlank() || raw == "null") return null
        val uri = Uri.parse(raw)
        if (uri.host != null && uri.host != siteHost) return null
        val path = if (uri.host != null) uri.encodedPath.orEmpty() else raw
        return if (path.startsWith("/media/") || path.startsWith("/static/")) SITE + path else null
    }

    /** Server bergan nisbiy havola (faqat /parent/ ostida) — tizim brauzerida ochish uchun. */
    fun siteUrl(path: String): String? =
        if (path.startsWith("/parent/") && !path.contains("..")) SITE + path else null
}

fun JSONObject.str(key: String): String = if (isNull(key)) "" else optString(key)
fun JSONObject.int(key: String): Int = if (isNull(key)) 0 else optDouble(key, 0.0).toInt()
fun JSONObject.intOrNull(key: String): Int? = if (!has(key) || isNull(key)) null else optDouble(key, 0.0).toInt()
fun JSONObject.dbl(key: String): Double = if (isNull(key)) 0.0 else optDouble(key, 0.0)
fun JSONObject.bool(key: String): Boolean = !isNull(key) && optBoolean(key)
fun JSONObject.strOrNull(key: String): String? = if (!has(key) || isNull(key)) null else optString(key).takeIf { it.isNotEmpty() }
fun JSONObject.obj(key: String): JSONObject? = if (!has(key) || isNull(key)) null else optJSONObject(key)
fun JSONObject.list(key: String): List<JSONObject> {
    val arr: JSONArray = optJSONArray(key) ?: return emptyList()
    return (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }
}
fun JSONObject.strings(key: String): List<String> {
    val arr: JSONArray = optJSONArray(key) ?: return emptyList()
    return (0 until arr.length()).map { arr.optString(it) }
}
