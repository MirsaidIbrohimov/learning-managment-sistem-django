package uz.itcacademy.parent

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.TimeUnit

/**
 * Farzand natija olsa, baholansa, darsga kelmasa, to'lov yaqinlashsa yoki markaz javob bersa — bildirishnoma.
 * Server push xizmati (Firebase) talab qilinmaydi: WorkManager har 15 daqiqada tekshiradi.
 */
object Notify {
    private const val WORK = "itcp-sync"
    private const val MAX_SEEN = 400

    private data class Channel(val id: String, val name: String, val desc: String)

    private val CHANNELS = listOf(
        Channel("results", "Natijalar va baholar", "Test natijalari, vazifa baholari, sertifikatlar"),
        Channel("attendance", "Davomat", "Darsga kelmagan yoki keçikkan kunlar"),
        Channel("payments", "Tölovlar", "Tölov eslatmalari va qabul qilingan tölovlar"),
        Channel("messages", "Xabarlar", "Öquv markazining javoblari va e'lonlari"),
    )

    private fun channelFor(kind: String) = when (kind) {
        "absent", "late" -> "attendance"
        "payment_due", "payment_ok" -> "payments"
        "reply", "notice" -> "messages"
        else -> "results"
    }

    fun createChannels(ctx: Context) {
        if (Build.VERSION.SDK_INT < 26) return
        val nm = ctx.getSystemService(NotificationManager::class.java)
        CHANNELS.forEach {
            nm.createNotificationChannel(NotificationChannel(it.id, it.name, NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = it.desc
                lockscreenVisibility = NotificationCompat.VISIBILITY_PRIVATE
            })
        }
    }

    fun schedule(ctx: Context) {
        val req = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(WORK, ExistingPeriodicWorkPolicy.KEEP, req)
    }

    fun cancel(ctx: Context) {
        WorkManager.getInstance(ctx).cancelUniqueWork(WORK)
        NotificationManagerCompat.from(ctx).cancelAll()
        ctx.getSharedPreferences("itcp_notify", Context.MODE_PRIVATE).edit().clear().apply()
    }

    fun allowed(ctx: Context): Boolean =
        Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    private fun iso(ms: Long): String =
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }.format(Date(ms))

    /**
     * Serverdan yangi voqealarni oladi va hali ko'rsatilmaganlarini chiqaradi.
     * Birinchi marta faqat "ko'rildi" deb belgilaydi — eski voqealar bilan bezovta qilmaydi.
     */
    suspend fun sync(ctx: Context) {
        if (Api.token == null) return
        val prefs = ctx.getSharedPreferences("itcp_notify", Context.MODE_PRIVATE)
        val since = prefs.getString("since", null)
        val r = Api.get("notifications/", mapOf("since" to since), fresh = true)
        val events = r.list("events")
        val seen = prefs.getStringSet("seen", emptySet()).orEmpty()
        val fresh = events.filter { it.str("id") !in seen }
        if (since != null && Settings.notify && allowed(ctx)) {
            fresh.take(6).reversed().forEach { show(ctx, it) }
            if (fresh.size > 6) summary(ctx, fresh.size)
        }
        val keep = (seen + fresh.map { it.str("id") }).toList().takeLast(MAX_SEEN).toSet()
        // Kursor ozgina orqada: server vaqti bilan farq bo'lsa ham voqea tushib qolmaydi (takror ID'lar o'tkaziladi)
        prefs.edit().putStringSet("seen", keep).putString("since", iso(System.currentTimeMillis() - 10 * 60_000L)).apply()
    }

    private fun openIntent(ctx: Context, target: String?, childId: Int, code: Int): PendingIntent {
        val i = Intent(ctx, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("target", target)
            putExtra("child_id", childId)
        }
        return PendingIntent.getActivity(ctx, code, i, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    @android.annotation.SuppressLint("MissingPermission")
    private fun show(ctx: Context, e: JSONObject) {
        val id = e.str("id").hashCode()
        val channel = channelFor(e.str("kind"))
        // Qulflangan ekranda tafsilot ko'rinmaydi
        val public = NotificationCompat.Builder(ctx, channel)
            .setSmallIcon(R.drawable.ic_notify)
            .setContentTitle("ITC Ota Ona")
            .setContentText("Yangi bildirişnoma")
            .build()
        val n = NotificationCompat.Builder(ctx, channel)
            .setSmallIcon(R.drawable.ic_notify)
            .setColor(0xFF8B5CF6.toInt())
            .setContentTitle(e.str("title"))
            .setContentText(e.str("text"))
            .setStyle(NotificationCompat.BigTextStyle().bigText(e.str("text")))
            .setAutoCancel(true)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(public)
            .setCategory(NotificationCompat.CATEGORY_EVENT)
            .setGroup("itcp")
            .setContentIntent(openIntent(ctx, e.str("target"), e.int("child_id"), id))
            .build()
        NotificationManagerCompat.from(ctx).notify(id, n)
    }

    @android.annotation.SuppressLint("MissingPermission")
    private fun summary(ctx: Context, count: Int) {
        val n = NotificationCompat.Builder(ctx, "results")
            .setSmallIcon(R.drawable.ic_notify)
            .setContentTitle("ITC Ota Ona")
            .setContentText("$count ta yangi bildirişnoma")
            .setGroup("itcp").setGroupSummary(true).setAutoCancel(true)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setContentIntent(openIntent(ctx, "notifications", 0, 1))
            .build()
        NotificationManagerCompat.from(ctx).notify(1, n)
    }
}

class SyncWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        Secure.init(applicationContext)
        Settings.init(applicationContext)
        if (Api.token == null) return Result.success()
        return try {
            Notify.sync(applicationContext)
            Result.success()
        } catch (e: ApiError) {
            if (e.status == 0 || e.status >= 500) Result.retry() else Result.success()
        }
    }
}
