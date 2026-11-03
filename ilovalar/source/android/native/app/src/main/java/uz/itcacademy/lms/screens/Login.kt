package uz.itcacademy.lms.screens

import android.util.Base64
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.Icon
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import uz.itcacademy.lms.*
import uz.itcacademy.lms.ui.*
import java.security.MessageDigest
import java.security.SecureRandom

@Composable
fun LoginScreen(onDone: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var login by remember { mutableStateOf(Settings.lastLogin) }
    var password by remember { mutableStateOf("") }
    var show by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var waiting by remember { mutableStateOf<JSONObject?>(null) }
    var left by remember { mutableIntStateOf(0) }
    var pollJob by remember { mutableStateOf<kotlinx.coroutines.Job?>(null) }

    fun authError(e: ApiError) = when (e.code) {
        "role", "blocked", "rate_limited" -> e.message.orEmpty()
        "denied" -> "Kiriş rad etildi"
        "expired", "consumed" -> "Kutiş vaqti tugadi. Qaytadan urinib köring"
        "invalid" -> "Login yoki parol notöğri"
        else -> if (e.status == 400) "Login yoki parol notöğri" else e.message.orEmpty()
    }

    fun submit() {
        error = null
        if (login.isBlank() || password.isEmpty()) { error = "Login va parolni kiriting"; return }
        busy = true
        scope.launch {
            try {
                val r = Api.post("/api/v1/app/login/", JSONObject().put("login", login.trim()).put("password", password))
                Api.token = r.getString("token")
                Settings.lastLogin = login.trim()
                onDone()
            } catch (e: ApiError) {
                error = authError(e)
            }
            busy = false
        }
    }

    // Brauzer orqali kirish (RFC 8252 + PKCE): Google, GitHub, Telegram, email kodi
    fun startBrowser() {
        error = null
        busy = true
        pollJob = scope.launch {
            val bytes = ByteArray(48).also { SecureRandom().nextBytes(it) }
            val flags = Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING
            val verifier = Base64.encodeToString(bytes, flags)
            val challenge = Base64.encodeToString(MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray()), flags)
            try {
                val info = Api.post("/api/v1/app/auth/start/", JSONObject().put("code_challenge", challenge))
                busy = false
                waiting = info
                openBrowser(ctx, info.getString("approve_url"))
                val deadline = System.currentTimeMillis() + info.optInt("expires_in", 600) * 1000L
                val interval = info.optInt("interval", 2).coerceAtLeast(1) * 1000L
                val poll = JSONObject().put("request_id", info.getString("request_id")).put("code_verifier", verifier)
                while (System.currentTimeMillis() < deadline) {
                    left = ((deadline - System.currentTimeMillis()) / 1000).toInt()
                    delay(interval)
                    try {
                        val r = Api.post("/api/v1/app/auth/poll/", poll)
                        if (r.optString("token").isNotEmpty()) {
                            Api.token = r.getString("token")
                            waiting = null
                            onDone()
                            return@launch
                        }
                    } catch (e: ApiError) {
                        if (e.status != 0) { waiting = null; error = authError(e); return@launch }
                    }
                }
                waiting = null
                error = "Kutiş vaqti tugadi. Qaytadan urinib köring"
            } catch (e: ApiError) {
                busy = false
                error = authError(e)
            }
        }
    }

    Box(Modifier.fillMaxSize()) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).statusBarsPadding().navigationBarsPadding().imePadding().padding(18.dp),
            verticalArrangement = Arrangement.Center,
        ) {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterEnd) { LanguageMenu() }
            Spacer(Modifier.height(20.dp))
            Txt("IT Creative Academy", size = 15.sp, weight = FontWeight.SemiBold, color = pal.text2, translate = false)
            Txt("Bilim — eng işonçli sarmoya.", size = 34.sp, weight = FontWeight.Bold, spacing = (-1).sp, modifier = Modifier.padding(top = 6.dp, bottom = 22.dp))

            val w = waiting
            Column(Modifier.reveal(0).glassBlur(RoundedCornerShape(28.dp)).padding(22.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                if (w != null) {
                    Txt("Brauzerda tasdiqlang", size = 24.sp, weight = FontWeight.Bold)
                    Muted("Brauzerda ITC Academy sayti oçildi. Saytga istalgan usulda kiring va quyidagi kod bilan bir xil kodni körib «Tasdiqlaş» ni bosing.", size = 13.5.sp)
                    Box(Modifier.fillMaxWidth().card().padding(16.dp), contentAlignment = Alignment.Center) {
                        Txt(w.str("user_code"), size = 32.sp, weight = FontWeight.ExtraBold, spacing = 6.sp, translate = false, align = TextAlign.Center)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Spinner(16.dp); Spacer(Modifier.width(10.dp))
                        Txt("Tasdiq kutilmoqda…", Modifier.weight(1f), color = pal.text2, size = 13.sp)
                        Muted("%d:%02d".format(left / 60, left % 60), translate = false)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Btn("Brauzerni qayta oçiş", Modifier.weight(1f), small = true, icon = Icons.Rounded.OpenInNew) { openBrowser(ctx, w.getString("approve_url")) }
                        Btn("Bekor qiliş", kind = BtnKind.Ghost, small = true) { pollJob?.cancel(); waiting = null }
                    }
                } else {
                    Txt("Xuş kelibsiz", size = 28.sp, weight = FontWeight.Bold, spacing = (-.6).sp)
                    Muted("Davom etiş uçun hisobingizga kiring", size = 14.sp)
                    AnimatedVisibility(error != null) {
                        Row(
                            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(pal.red.copy(alpha = .13f)).padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(Icons.Rounded.ErrorOutline, null, Modifier.size(18.dp), pal.red); Spacer(Modifier.width(8.dp))
                            Txt(error.orEmpty(), color = pal.red, size = 13.sp, weight = FontWeight.Medium)
                        }
                    }
                    Field(login, { login = it }, "Foydalanuvçi nomi yoki +998…", icon = Icons.Rounded.Person)
                    Field(
                        password, { password = it }, "Parol", icon = Icons.Rounded.Lock, password = !show,
                        trailing = {
                            Icon(
                                if (show) Icons.Rounded.VisibilityOff else Icons.Rounded.Visibility, t("Parolni körsatiş"),
                                Modifier.size(22.dp).press { show = !show }, pal.muted,
                            )
                        },
                    )
                    Btn("Kiriş", Modifier.fillMaxWidth(), BtnKind.Primary, busy = busy, icon = Icons.Rounded.ArrowForward) { submit() }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Hairline2(Modifier.weight(1f)); Muted("yoki", Modifier.padding(horizontal = 10.dp)); Hairline2(Modifier.weight(1f))
                    }
                    Row(
                        Modifier.fillMaxWidth().press { startBrowser() }.card(RoundedCornerShape(16.dp)).padding(14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        IcoBox(Icons.Rounded.Language, pal.a1)
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Txt("Sayt orqali kiriş", weight = FontWeight.SemiBold)
                            Muted("Google, GitHub, Telegram, email kodi va boşqalar", size = 12.sp)
                        }
                        Icon(Icons.Rounded.OpenInNew, null, Modifier.size(17.dp), pal.muted)
                    }
                    Muted("Ilova faqat öquvçilar uçun", Modifier.align(Alignment.CenterHorizontally))
                    Row(Modifier.align(Alignment.CenterHorizontally), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                        Txt("Saytda röyxatdan öting", Modifier.press { openBrowser(ctx, "${Api.SITE}/register/") }, size = 13.sp, weight = FontWeight.SemiBold)
                        Txt("Parolni unutdingizmi?", Modifier.press { openBrowser(ctx, "${Api.SITE}/login/") }, size = 13.sp, color = pal.muted)
                    }
                }
            }
        }
    }
}

@Composable
private fun Hairline2(modifier: Modifier) = Box(modifier.height(1.dp).background(pal.border))

/** Bayroqli til tanlash: pastdan shisha varaq ochiladi. */
@Composable
fun LanguageMenu() {
    val cur = Settings.lang
    Row(
        Modifier.press { Sheets.show { close ->
            Txt("Til", size = 19.sp, weight = FontWeight.Bold, modifier = Modifier.padding(bottom = 10.dp))
            I18n.LANGS.forEach { (k, name) ->
                Row(
                    Modifier.fillMaxWidth().press(scale = .98f) { Settings.update { lang = k }; close() }.padding(vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Flag(k, Modifier.size(36.dp, 24.dp))
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Txt(name, weight = FontWeight.SemiBold, size = 15.sp, translate = false)
                        Muted(I18n.COUNTRY[k].orEmpty(), translate = false)
                    }
                    if (k == Settings.lang) Icon(Icons.Rounded.Check, null, Modifier.size(20.dp), pal.a1)
                }
            }
        } }.card(RoundedCornerShape(14.dp), pal.surface2).padding(horizontal = 12.dp, vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Flag(cur, Modifier.size(24.dp, 16.dp))
        Spacer(Modifier.width(8.dp))
        Txt(I18n.LANGS.first { it.first == cur }.second, size = 13.sp, weight = FontWeight.SemiBold, translate = false)
        Icon(Icons.Rounded.ExpandMore, null, Modifier.size(16.dp), pal.muted)
    }
}
