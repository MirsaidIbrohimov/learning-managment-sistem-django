package uz.itcacademy.lms

import android.content.Context
import android.content.SharedPreferences
import android.net.Uri
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

/** Tanlangan yoki yozib olingan fayl. */
class PickedFile(val name: String, val mime: String?, val bytes: ByteArray)

class ApiError(val status: Int, val data: JSONObject?) : Exception(messageFor(status, data)) {
    val code: String? get() = data?.optString("code")?.takeIf { it.isNotEmpty() }
}

private fun messageFor(status: Int, data: JSONObject?): String {
    if (status == 0) return "Internet aloqasi yöq yoki server javob bermayapti"
    if (data != null) {
        data.optString("error").takeIf { it.isNotEmpty() }?.let { return it }
        data.optString("detail").takeIf { it.isNotEmpty() }?.let { return translateDetail(it) }
        val keys = data.keys()
        while (keys.hasNext()) {
            when (val v = data.get(keys.next())) {
                is JSONArray -> if (v.length() > 0 && v.get(0) is String) return translateDetail(v.getString(0))
                is String -> if (v.isNotEmpty()) return translateDetail(v)
            }
        }
    }
    return when {
        status == 401 -> "Sessiya tugadi. Qaytadan kiring"
        status == 403 -> "Bu amal uçun ruxsat yöq"
        status == 404 -> "Topilmadi"
        status == 429 -> "Juda köp sörov. Birozdan keyin urinib köring"
        status >= 500 -> "Serverda xatolik. Keyinroq urinib köring"
        else -> "Kutilmagan xatolik"
    }
}

private fun translateDetail(s: String) = when {
    s == "Unable to log in with provided credentials." -> "Login yoki parol notöğri"
    s == "Authentication credentials were not provided." || s == "Invalid token." -> "Sessiya tugadi. Qaytadan kiring"
    s == "You do not have permission to perform this action." -> "Bu amal uçun ruxsat yöq"
    s == "Not found." -> "Topilmadi"
    s == "This field may not be blank." -> "Maydonni töldiring"
    s.startsWith("Request was throttled") -> "Juda köp sörov. Birozdan keyin urinib köring"
    s == "Retries aren't allowed for this quiz." -> "Bu testni qayta topşirib bölmaydi"
    s == "You've used all of your attempts for this quiz." -> "Urinişlar soni tugagan"
    s == "This quiz has no questions yet." -> "Bu testda hali savollar yöq"
    s == "You're not enrolled in this course." -> "Avval kursga yoziling!"
    s == "This attempt is no longer in progress." -> "Test vaqti tugagan"
    else -> s
}

/** itc-academy.uz API mijozi. Token shifrlangan xotirada saqlanadi va faqat o'z saytiga yuboriladi. */
object Api {
    val SITE: String = BuildConfig.SITE
    private val siteHost: String = Uri.parse(SITE).host.orEmpty()
    private const val USER_AGENT = "ITC-Academy-Android/${BuildConfig.VERSION_NAME} (Android; Mobile)"
    private val JSON = "application/json".toMediaType()
    private const val FRESH_MS = 45_000L

    private lateinit var secure: SharedPreferences
    private val cache = ConcurrentHashMap<String, Pair<Long, Any>>()
    var onUnauthorized: (() -> Unit)? = null

    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .followRedirects(false)
        .addInterceptor(Interceptor { chain ->
            val b = chain.request().newBuilder().header("User-Agent", USER_AGENT)
            val t = token
            // Token faqat o'z saytimizga: rasm havolasi boshqa domenga olib ketsa ham chiqib ketmaydi
            if (t != null && chain.request().url.host == siteHost) b.header("Authorization", "Token $t")
            chain.proceed(b.build())
        })
        .build()

    fun init(ctx: Context) {
        val key = MasterKey.Builder(ctx).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
        secure = EncryptedSharedPreferences.create(
            ctx, "itc_secure", key,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    var token: String?
        get() = if (::secure.isInitialized) secure.getString("token", null) else null
        set(v) {
            secure.edit().apply { if (v == null) remove("token") else putString("token", v) }.apply()
        }

    fun clearCache() = cache.clear()

    private fun url(path: String, params: Map<String, Any?>?): String {
        val b = Uri.parse(SITE + path).buildUpon()
        params?.forEach { (k, v) -> if (v != null && v.toString().isNotEmpty()) b.appendQueryParameter(k, v.toString()) }
        return b.build().toString()
    }

    private suspend fun call(method: String, url: String, body: JSONObject?, raw: RequestBody? = null): Any = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(url).header("Accept", "application/json")
        when (method) {
            "GET" -> req.get()
            else -> req.method(method, raw ?: (body ?: JSONObject()).toString().toRequestBody(JSON))
        }
        try {
            client.newCall(req.build()).execute().use { r ->
                val text = r.body?.string().orEmpty()
                val parsed: Any? = runCatching {
                    if (text.trimStart().startsWith("[")) JSONArray(text) else JSONObject(text)
                }.getOrNull()
                if (r.isSuccessful) return@withContext parsed ?: JSONObject()
                if (r.code == 401) {
                    token = null
                    withContext(Dispatchers.Main) { onUnauthorized?.invoke() }
                }
                throw ApiError(r.code, parsed as? JSONObject)
            }
        } catch (e: IOException) {
            throw ApiError(0, null)
        }
    }

    suspend fun getAny(path: String, params: Map<String, Any?>? = null, fresh: Boolean = false): Any {
        val u = url(path, params)
        if (!fresh) cache[u]?.let { (t, d) -> if (System.currentTimeMillis() - t < FRESH_MS) return d }
        return call("GET", u, null).also { cache[u] = System.currentTimeMillis() to it }
    }

    suspend fun get(path: String, params: Map<String, Any?>? = null, fresh: Boolean = false): JSONObject =
        getAny(path, params, fresh) as? JSONObject ?: JSONObject()

    suspend fun post(path: String, body: JSONObject = JSONObject()): JSONObject {
        try {
            return call("POST", url(path, null), body) as? JSONObject ?: JSONObject()
        } finally { clearCache() }
    }

    suspend fun patch(path: String, body: JSONObject): JSONObject {
        try {
            return call("PATCH", url(path, null), body) as? JSONObject ?: JSONObject()
        } finally { clearCache() }
    }

    /** Fayl va matn maydonlarini multipart bilan yuboradi. */
    suspend fun upload(path: String, fields: Map<String, String>, fileField: String? = null, file: PickedFile? = null): JSONObject {
        val b = MultipartBody.Builder().setType(MultipartBody.FORM)
        fields.forEach { (k, v) -> b.addFormDataPart(k, v) }
        if (fileField != null && file != null) {
            b.addFormDataPart(fileField, file.name, file.bytes.toRequestBody((file.mime ?: "application/octet-stream").toMediaTypeOrNull()))
        }
        try {
            return call("POST", url(path, null), null, b.build()) as? JSONObject ?: JSONObject()
        } finally { clearCache() }
    }

    /** Sahifalangan ro'yxatni to'liq yig'adi (eng ko'pi bilan `max` sahifa). */
    suspend fun getAll(path: String, params: Map<String, Any?>? = null, max: Int = 15): List<JSONObject> {
        var data = getAny(path, params)
        val out = rows(data).toMutableList()
        var n = 1
        while (data is JSONObject && data.optString("next").let { it.isNotEmpty() && it != "null" } && n < max) {
            val next = Uri.parse(data.getString("next"))
            data = getAny(next.path + "?" + next.query)
            out += rows(data)
            n++
        }
        return out
    }

    fun rows(data: Any?): List<JSONObject> {
        val arr = when (data) {
            is JSONArray -> data
            is JSONObject -> data.optJSONArray("results")
            else -> null
        } ?: return emptyList()
        return (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }
    }

    /** Sayt rasmi uchun to'liq manzil. Faqat o'z saytimizning /media va /static yo'llari. */
    fun media(raw: String?): String? {
        if (raw.isNullOrBlank() || raw == "null") return null
        val uri = Uri.parse(raw)
        if (uri.host != null && uri.host != siteHost && uri.host?.endsWith(".$siteHost") != true) return null
        val path = if (uri.host != null) (uri.encodedPath.orEmpty() + (uri.encodedQuery?.let { "?$it" } ?: "")) else raw
        return if (path.startsWith("/media/") || path.startsWith("/static/")) SITE + path else null
    }

    /** Saytdagi sahifa uchun bir martalik kirish havolasi. Olib bo'lmasa oddiy manzil. */
    suspend fun webUrl(path: String): String = try {
        val r = post("/api/v1/app/web-login/", JSONObject().put("path", path))
        r.optString("url").takeIf { it.startsWith("/app/web-login/") }?.let { SITE + it } ?: (SITE + path)
    } catch (e: ApiError) {
        SITE + path
    }
}

fun JSONObject.str(key: String): String = if (isNull(key)) "" else optString(key)
fun JSONObject.int(key: String): Int = if (isNull(key)) 0 else optDouble(key, 0.0).toInt()
fun JSONObject.bool(key: String): Boolean = !isNull(key) && optBoolean(key)
fun JSONObject.strOrNull(key: String): String? = if (isNull(key)) null else optString(key).takeIf { it.isNotEmpty() }
