package uz.itcacademy.parent

import android.os.SystemClock
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

/**
 * PIN-kod. Kodning o'zi saqlanmaydi: PBKDF2-SHA256 (120 000 marta) xeshi va tasodifiy tuz
 * shifrlangan xotirada turadi.
 *
 * Noto'g'ri urinishlar: 5 tadan keyin 30 soniya, keyin har safar ikki barobar ko'p kutish.
 * Jami 10 ta noto'g'ri urinishdan so'ng hisobdan avtomatik chiqiladi.
 */
object Pin {
    const val LENGTH = 4
    const val FREE_TRIES = 5
    const val MAX_TRIES = 10
    private const val ITERATIONS = 120_000

    /** Juda oson taxmin qilinadigan kodlar. */
    private val WEAK = setOf("1234", "4321", "1212", "1122", "1004", "2000", "2580", "0852", "6969", "1010", "0123", "9876")

    val isSet: Boolean get() = Secure.prefs.contains("pin.hash")

    fun weakReason(pin: String): String? = when {
        pin.length != LENGTH || !pin.all { it.isDigit() } -> "PIN $LENGTH ta raqamdan iborat bölişi kerak"
        pin.toSet().size == 1 -> "Bir xil raqamlardan iborat PIN juda oson"
        pin in WEAK || "0123456789".contains(pin) || "9876543210".contains(pin) -> "Bu PIN juda oson topiladi. Boşqasini tanlang"
        else -> null
    }

    private fun derive(pin: String, salt: ByteArray): ByteArray =
        SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
            .generateSecret(PBEKeySpec(pin.toCharArray(), salt, ITERATIONS, 256)).encoded

    private fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it) }
    private fun unhex(s: String) = ByteArray(s.length / 2) { s.substring(it * 2, it * 2 + 2).toInt(16).toByte() }

    fun set(pin: String) {
        val salt = ByteArray(16).also { SecureRandom().nextBytes(it) }
        Secure.prefs.edit()
            .putString("pin.salt", hex(salt))
            .putString("pin.hash", hex(derive(pin, salt)))
            .putInt("pin.fails", 0).remove("pin.until")
            .apply()
    }

    sealed class Result {
        data object Ok : Result()
        data class Wrong(val left: Int) : Result()
        data class Locked(val seconds: Int) : Result()
        data object Wipe : Result()
    }

    val fails: Int get() = Secure.prefs.getInt("pin.fails", 0)

    /** Qancha soniya kutish kerak (0 — kiritish mumkin). */
    fun lockedSeconds(): Int {
        val until = Secure.prefs.getLong("pin.until", 0L)
        val now = System.currentTimeMillis()
        // Soat orqaga surilsa ham bloklash qisqarmaydi: oxirgi ko'rilgan vaqt saqlanadi
        val seen = Secure.prefs.getLong("pin.seen", 0L)
        val t = maxOf(now, seen)
        if (now > seen) Secure.prefs.edit().putLong("pin.seen", now).apply()
        return if (until > t) ((until - t + 999) / 1000).toInt() else 0
    }

    fun check(pin: String): Result {
        lockedSeconds().let { if (it > 0) return Result.Locked(it) }
        val salt = Secure.prefs.getString("pin.salt", null)?.let(::unhex) ?: return Result.Wipe
        val hash = Secure.prefs.getString("pin.hash", null)?.let(::unhex) ?: return Result.Wipe
        if (MessageDigest.isEqual(derive(pin, salt), hash)) {
            Secure.prefs.edit().putInt("pin.fails", 0).remove("pin.until").apply()
            return Result.Ok
        }
        val n = fails + 1
        val e = Secure.prefs.edit().putInt("pin.fails", n)
        if (n >= MAX_TRIES) { e.apply(); return Result.Wipe }
        if (n >= FREE_TRIES) {
            val wait = 30L shl (n - FREE_TRIES)   // 30, 60, 120, 240, 480 soniya
            e.putLong("pin.until", System.currentTimeMillis() + wait * 1000).apply()
            return Result.Locked(wait.toInt())
        }
        e.apply()
        return Result.Wrong(FREE_TRIES - n)
    }

    fun resetFails() = Secure.prefs.edit().putInt("pin.fails", 0).remove("pin.until").apply()

    var biometric: Boolean
        get() = Secure.prefs.getBoolean("pin.bio", false)
        set(v) = Secure.prefs.edit().putBoolean("pin.bio", v).apply()

    fun clear() {
        Secure.prefs.edit().remove("pin.hash").remove("pin.salt").remove("pin.fails").remove("pin.until").remove("pin.bio").apply()
    }
}

/** Ilova fonga o'tganda vaqtni eslab qoladi: qaytganda PIN so'raladimi. */
object AutoLock {
    /** Fondan shuncha vaqtdan keyin qaytilsa PIN qayta so'raladi. */
    private const val GRACE_MS = 30_000L
    private var hiddenAt = 0L

    fun onHidden() { hiddenAt = SystemClock.elapsedRealtime() }
    fun shouldLock(): Boolean = hiddenAt != 0L && SystemClock.elapsedRealtime() - hiddenAt > GRACE_MS
    fun reset() { hiddenAt = 0L }
}
