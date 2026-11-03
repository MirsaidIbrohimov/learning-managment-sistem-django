package uz.itcacademy.parent.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import org.json.JSONObject
import uz.itcacademy.parent.*
import uz.itcacademy.parent.ui.*

@Composable
fun LoginScreen(onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    var login by remember { mutableStateOf(Settings.lastLogin) }
    var password by remember { mutableStateOf("") }
    var show by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun submit() {
        error = null
        if (login.isBlank() || password.isEmpty()) { error = "Login va parolni kiriting"; return }
        busy = true
        scope.launch {
            try {
                val device = "${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}".trim()
                val r = Api.post("login/", JSONObject().put("login", login.trim()).put("password", password).put("device", device))
                Api.token = r.getString("token")
                Secure.prefs.edit().putString("name", r.optJSONObject("parent")?.optString("full_name").orEmpty()).apply()
                Settings.lastLogin = login.trim()
                password = ""
                onDone()
            } catch (e: ApiError) {
                error = e.message
            }
            busy = false
        }
    }

    val tr = rememberInfiniteTransition(label = "logo")
    val float by tr.animateFloat(0f, if (motionOn) -10f else 0f, infiniteRepeatable(tween(2200), RepeatMode.Reverse), label = "f")

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).statusBarsPadding().navigationBarsPadding().imePadding().padding(20.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Spacer(Modifier.height(30.dp))
        Box(
            Modifier.graphicsLayer { translationY = float }.size(76.dp).clip(RoundedCornerShape(24.dp))
                .background(Brush.linearGradient(listOf(pal.a1, pal.a2))),
            contentAlignment = Alignment.Center,
        ) { Icon(Icons.Rounded.FamilyRestroom, null, Modifier.size(40.dp), Color.White) }
        Spacer(Modifier.height(20.dp))
        Txt("ITC Ota Ona", size = 15.sp, weight = FontWeight.SemiBold, color = pal.text2)
        Txt("Farzandingiz öqişi — kaftingizda", size = 30.sp, weight = FontWeight.Bold, spacing = (-.8).sp,
            modifier = Modifier.padding(top = 4.dp, bottom = 22.dp))

        Column(Modifier.reveal(0).glassBlur(RoundedCornerShape(28.dp)).padding(22.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Txt("Hisobga kiriş", size = 19.sp, weight = FontWeight.Bold)
            Muted("Öquv markazi bergan login (yoki telefon raqam) va parolni kiriting", size = 13.5.sp)
            Field(login, { login = it; error = null }, "Login yoki telefon raqam", icon = Icons.Rounded.Person)
            Field(
                password, { password = it; error = null }, "Parol", icon = Icons.Rounded.Lock, password = !show,
                trailing = {
                    Icon(
                        if (show) Icons.Rounded.VisibilityOff else Icons.Rounded.Visibility, if (show) "Yaşiriş" else "Körsatiş",
                        Modifier.size(22.dp).press { show = !show }, pal.muted,
                    )
                },
            )
            AnimatedVisibility(error != null, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
                Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(pal.red.copy(alpha = .12f)).padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Rounded.ErrorOutline, null, Modifier.size(20.dp), pal.red)
                    Spacer(Modifier.width(8.dp))
                    Txt(error.orEmpty(), size = 13.5.sp, color = pal.red)
                }
            }
            Btn("Kiriş", Modifier.fillMaxWidth(), BtnKind.Primary, Icons.Rounded.Login, busy = busy) { submit() }
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                Txt("Parolni unutdingizmi?", Modifier.press { resetSheet(login) }.padding(6.dp), 14.sp, FontWeight.SemiBold, pal.a1)
            }
        }
        Spacer(Modifier.height(16.dp))
        Row(Modifier.fillMaxWidth().padding(horizontal = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Rounded.VerifiedUser, null, Modifier.size(18.dp), pal.green)
            Spacer(Modifier.width(8.dp))
            Muted("Ma'lumotlar shifrlangan holda uzatiladi va saqlanadi. Kirgandan keyin PIN-kod örnatasiz.", size = 12.5.sp)
        }
    }
}

/** Parolni tiklash so'rovi: administrator tasdiqlaydi. */
private fun resetSheet(prefill: String) = Sheets.show { close ->
    val scope = rememberCoroutineScope()
    var login by remember { mutableStateOf(prefill) }
    var p1 by remember { mutableStateOf("") }
    var p2 by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var done by remember { mutableStateOf<String?>(null) }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        IcoBox(Icons.Rounded.LockReset, pal.a1, 46.dp)
        Txt("Parolni tiklaş", size = 20.sp, weight = FontWeight.Bold)
        if (done != null) {
            Muted(done!!, size = 14.sp)
            Btn("Tuşunarli", Modifier.fillMaxWidth(), BtnKind.Primary, onClick = close)
            return@Column
        }
        Muted("Yangi parolni kiriting. Administrator sörovni tasdiqlagaç, şu parol bilan kirasiz.", size = 13.5.sp)
        Field(login, { login = it }, "Login yoki telefon raqam", icon = Icons.Rounded.Person)
        Field(p1, { p1 = it }, "Yangi parol", icon = Icons.Rounded.Lock, password = true)
        Field(p2, { p2 = it }, "Yangi parolni takrorlang", icon = Icons.Rounded.Lock, password = true)
        if (error != null) Txt(error!!, size = 13.sp, color = pal.red)
        Btn("Sörov yuboriş", Modifier.fillMaxWidth(), BtnKind.Primary, Icons.Rounded.Send, busy = busy) {
            error = null
            busy = true
            scope.launch {
                try {
                    val r = Api.post("password-reset/", JSONObject().put("login", login.trim()).put("new_password", p1).put("confirm_password", p2))
                    done = r.optString("message")
                } catch (e: ApiError) { error = e.message }
                busy = false
            }
        }
    }
}
