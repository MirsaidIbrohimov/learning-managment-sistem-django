package uz.itcacademy.parent

import android.content.Context
import android.content.SharedPreferences
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/** Ko'rinish sozlamalari: o'zgarsa interfeys darhol yangilanadi. Maxfiy ma'lumot bu yerda saqlanmaydi. */
object Settings {
    private lateinit var p: SharedPreferences

    var theme by mutableStateOf("dark")
    var accent by mutableStateOf("violet")
    var motion by mutableStateOf(true)
    var notify by mutableStateOf(true)
    var largeText by mutableStateOf(false)

    fun init(ctx: Context) {
        if (::p.isInitialized) return
        p = ctx.getSharedPreferences("itcp_settings", Context.MODE_PRIVATE)
        theme = p.getString("theme", "dark") ?: "dark"
        accent = p.getString("accent", "violet") ?: "violet"
        motion = p.getBoolean("motion", true)
        notify = p.getBoolean("notify", true)
        largeText = p.getBoolean("largeText", false)
        tour = p.getBoolean("tourDone", false)
    }

    fun update(block: Settings.() -> Unit) {
        block()
        p.edit()
            .putString("theme", theme).putString("accent", accent)
            .putBoolean("motion", motion).putBoolean("notify", notify).putBoolean("largeText", largeText)
            .apply()
    }

    var lastLogin: String
        get() = p.getString("lastLogin", "") ?: ""
        set(v) = p.edit().putString("lastLogin", v).apply()

    private var tour by mutableStateOf(false)
    /** Kuzatiladi: qo'llanma "qayta ko'rish" bosilsa darhol ochiladi. */
    var tourDone: Boolean
        get() = tour
        set(v) { tour = v; p.edit().putBoolean("tourDone", v).apply() }

    var childId: Int
        get() = p.getInt("childId", 0)
        set(v) = p.edit().putInt("childId", v).apply()

    var askedNotify: Boolean
        get() = p.getBoolean("askedNotify", false)
        set(v) = p.edit().putBoolean("askedNotify", v).apply()

    /** Hisobdan chiqilganda: qurilmada shu hisobga oid hech narsa qolmaydi. */
    fun clearAccount() {
        p.edit().remove("childId").remove("tourDone").remove("askedNotify").apply()
        tour = false
    }
}

/** Interfeys o'zbekcha. Kelajakda tarjima qo'shilsa shu yerdan o'tadi. */
fun t(s: String) = s
