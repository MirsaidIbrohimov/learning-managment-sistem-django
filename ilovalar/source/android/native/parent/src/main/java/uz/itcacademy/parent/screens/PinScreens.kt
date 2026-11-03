package uz.itcacademy.parent.screens

import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_STRONG
import androidx.biometric.BiometricPrompt
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.keyframes
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import uz.itcacademy.parent.*
import uz.itcacademy.parent.ui.*

/** Barmoq izi / yuz orqali ochish (faqat kuchli biometrika). */
object Bio {
    fun available(act: FragmentActivity): Boolean =
        BiometricManager.from(act).canAuthenticate(BIOMETRIC_STRONG) == BiometricManager.BIOMETRIC_SUCCESS

    fun prompt(act: FragmentActivity, title: String, onOk: () -> Unit, onFail: (String?) -> Unit = {}) {
        val cb = object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) = onOk()
            override fun onAuthenticationError(code: Int, msg: CharSequence) {
                val cancelled = code == BiometricPrompt.ERROR_USER_CANCELED || code == BiometricPrompt.ERROR_NEGATIVE_BUTTON || code == BiometricPrompt.ERROR_CANCELED
                onFail(if (cancelled) null else msg.toString())
            }
        }
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle(title)
            .setSubtitle("ITC Ota Ona")
            .setNegativeButtonText("PIN-kod bilan")
            .setAllowedAuthenticators(BIOMETRIC_STRONG)
            .setConfirmationRequired(false)
            .build()
        BiometricPrompt(act, ContextCompat.getMainExecutor(act), cb).authenticate(info)
    }
}

/** Raqamli klaviatura va to'ldiriladigan nuqtalar. */
@Composable
fun PinPad(
    title: String,
    subtitle: String,
    icon: ImageVector,
    error: String?,
    shakeKey: Int,
    enabled: Boolean = true,
    bioIcon: Boolean = false,
    onBio: () -> Unit = {},
    footer: (@Composable () -> Unit)? = null,
    onComplete: (String) -> Unit,
) {
    val p = pal
    val haptic = LocalHapticFeedback.current
    var code by remember { mutableStateOf("") }
    val shake = remember { Animatable(0f) }
    LaunchedEffect(shakeKey) {
        if (shakeKey == 0) return@LaunchedEffect
        code = ""
        haptic.performHapticFeedback(HapticFeedbackType.LongPress)
        if (motionOn) shake.animateTo(0f, keyframes {
            durationMillis = 420
            -22f at 50; 20f at 110; -16f at 170; 12f at 230; -6f at 300; 0f at 420
        })
    }
    LaunchedEffect(title) { code = "" }

    // Yangi raqam terilishi bilan eski xato yashiriladi (bloklangan holatda tugmalar o'chiq, xato qoladi)
    var typed by remember(shakeKey, error) { mutableStateOf(false) }
    val shownError = if (typed) null else error

    fun press(d: String) {
        if (!enabled || code.length >= Pin.LENGTH) return
        typed = true
        code += d
        if (code.length == Pin.LENGTH) onComplete(code)
    }

    val header: @Composable () -> Unit = {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            val pulse by animateFloatAsState(if (shownError != null) .92f else 1f, spring(.4f, Spring.StiffnessMedium), label = "lock")
            Box(
                Modifier.graphicsLayer { scaleX = pulse; scaleY = pulse }.size(72.dp).clip(RoundedCornerShape(24.dp))
                    .background(Brush.linearGradient(listOf(p.a1, p.a2))),
                contentAlignment = Alignment.Center,
            ) { Icon(icon, null, Modifier.size(36.dp), Color.White) }
            Spacer(Modifier.height(16.dp))
            AnimatedContent(title, transitionSpec = {
                (slideInHorizontally { it / 3 } + fadeIn()) togetherWith (slideOutHorizontally { -it / 3 } + fadeOut())
            }, label = "title") { t -> Txt(t, size = 21.sp, weight = FontWeight.Bold, align = TextAlign.Center) }
            Muted(subtitle, Modifier.padding(top = 4.dp), 14.sp)
            Row(Modifier.padding(vertical = 22.dp).graphicsLayer { translationX = shake.value }, horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                repeat(Pin.LENGTH) { i ->
                    val filled = i < code.length
                    val s by animateFloatAsState(if (filled) 1.15f else 1f, spring(.35f, Spring.StiffnessMedium), label = "dot")
                    Box(
                        Modifier.graphicsLayer { scaleX = s; scaleY = s }.size(16.dp).clip(CircleShape)
                            .then(if (filled) Modifier.background(if (shownError != null) p.red else p.text) else Modifier.border(2.dp, p.muted, CircleShape)),
                    )
                }
            }
            Box(Modifier.heightIn(min = 22.dp), contentAlignment = Alignment.Center) {
                if (shownError != null) Txt(shownError, size = 13.5.sp, color = p.red, align = TextAlign.Center, weight = FontWeight.Medium)
            }
        }
    }

    @Composable
    fun Keypad(key: androidx.compose.ui.unit.Dp) {
        val rows = listOf(listOf("1", "2", "3"), listOf("4", "5", "6"), listOf("7", "8", "9"), listOf("bio", "0", "del"))
        Column(verticalArrangement = Arrangement.spacedBy(key * .18f)) {
            rows.forEach { row ->
                Row(horizontalArrangement = Arrangement.spacedBy(key * .32f)) {
                    row.forEach { k ->
                        val keyMod = Modifier.size(key)
                        when (k) {
                            "bio" -> if (bioIcon) Box(keyMod.clip(CircleShape).press(enabled) { onBio() }, contentAlignment = Alignment.Center) {
                                Icon(Icons.Rounded.Fingerprint, "Barmoq izi", Modifier.size(key * .46f), p.a1)
                            } else Spacer(keyMod)
                            "del" -> Box(keyMod.clip(CircleShape).press(enabled && code.isNotEmpty()) { code = code.dropLast(1) }, contentAlignment = Alignment.Center) {
                                Icon(Icons.Rounded.Backspace, "Öçiriş", Modifier.size(key * .35f), if (code.isEmpty()) p.muted else p.text)
                            }
                            else -> Box(
                                keyMod.clip(CircleShape).background(p.surface2).border(1.dp, p.border, CircleShape)
                                    .press(enabled, scale = .88f) { press(k) }
                                    .graphicsLayer { alpha = if (enabled) 1f else .4f },
                                contentAlignment = Alignment.Center,
                            ) { Txt(k, size = (key.value * .38f).sp, weight = FontWeight.Medium) }
                        }
                    }
                }
            }
        }
    }

    BoxWithConstraints(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().padding(horizontal = 24.dp, vertical = 12.dp)) {
        if (maxWidth > maxHeight) {
            // Yotiq holat: chapda sarlavha, o'ngda klaviatura — hammasi ekranga sig'adi
            val key = ((maxHeight - 40.dp) / 4.6f).coerceIn(44.dp, 74.dp)
            Row(Modifier.fillMaxSize(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                    header()
                    footer?.invoke()
                }
                Box(Modifier.weight(1f), contentAlignment = Alignment.Center) { Keypad(key) }
            }
        } else {
            val key = ((maxHeight - 330.dp) / 4.7f).coerceIn(52.dp, 76.dp)
            Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally) {
                Spacer(Modifier.weight(.6f))
                header()
                Spacer(Modifier.height(12.dp))
                Keypad(key)
                Spacer(Modifier.weight(1f))
                footer?.invoke()
            }
        }
    }
}

/** Birinchi kirishdan keyin: PIN o'rnatish (ikki marta), keyin barmoq izini yoqish taklifi. */
@Composable
fun SetPinScreen(onDone: () -> Unit, changing: Boolean = false) {
    val ctx = LocalContext.current
    val act = ctx as FragmentActivity
    var first by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var shake by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()

    fun finish() {
        if (!changing && Bio.available(act)) {
            Sheets.show { close ->
                IcoBox(Icons.Rounded.Fingerprint, pal.a1, 48.dp)
                Spacer(Modifier.height(12.dp))
                Txt("Barmoq izi bilan oçilsinmi?", size = 19.sp, weight = FontWeight.Bold)
                Muted("Har safar PIN terib öltirmasdan, barmoq izi yoki yuz orqali tez kirasiz. Buni keyin Sozlamalarda özgartiriş mumkin.",
                    Modifier.padding(top = 6.dp, bottom = 18.dp), 14.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Btn("Keyinroq", Modifier.weight(1f)) { close(); onDone() }
                    Btn("Yoqiş", Modifier.weight(1f), BtnKind.Primary, Icons.Rounded.Fingerprint) {
                        Bio.prompt(act, "Barmoq izini tasdiqlang", onOk = {
                            Pin.biometric = true
                            Toasts.show("Barmoq izi yoqildi")
                            close(); onDone()
                        }, onFail = { msg -> if (msg != null) Toasts.show(msg, "err") })
                    }
                }
            }
        } else onDone()
    }

    PinPad(
        title = if (first == null) (if (changing) "Yangi PIN-kod" else "PIN-kod örnating") else "PIN-kodni takrorlang",
        subtitle = if (first == null) "Ilovaga har kirganda şu ${Pin.LENGTH} xonali kod söraladi" else "Tasdiqlaş uçun yana bir bor kiriting",
        icon = if (first == null) Icons.Rounded.Pin else Icons.Rounded.VerifiedUser,
        error = error, shakeKey = shake,
    ) { code ->
        if (first == null) {
            val weak = Pin.weakReason(code)
            if (weak != null) { error = weak; shake++; return@PinPad }
            error = null
            first = code
        } else if (code != first) {
            error = "PIN-kodlar mos kelmadi. Qaytadan boşlang"
            first = null
            shake++
        } else {
            scope.launch {
                withContext(Dispatchers.Default) { Pin.set(code) }
                Toasts.show(if (changing) "PIN-kod yangilandi" else "PIN-kod örnatildi")
                finish()
            }
        }
    }
}

/** Ilova ochilganda: PIN yoki barmoq izi. */
@Composable
fun LockScreen(activity: FragmentActivity, onUnlock: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var error by remember { mutableStateOf<String?>(null) }
    var shake by remember { mutableIntStateOf(0) }
    var locked by remember { mutableIntStateOf(Pin.lockedSeconds()) }
    var checking by remember { mutableStateOf(false) }
    val bio = Pin.biometric && Bio.available(activity)
    val name = Secure.prefs.getString("name", "").orEmpty()

    LaunchedEffect(locked) {
        while (locked > 0) {
            error = "Juda köp xato. $locked soniyadan keyin urinib köring"
            delay(1000)
            locked = Pin.lockedSeconds()
            if (locked == 0) error = null
        }
    }
    fun askBio() = Bio.prompt(activity, "ITC Ota Ona'ni oçiş", onOk = { Pin.resetFails(); onUnlock() })
    LaunchedEffect(Unit) { if (bio && locked == 0) { delay(350); askBio() } }

    PinPad(
        title = if (name.isNotEmpty()) "Xuş kelibsiz, ${name.substringBefore(' ')}" else "Xuş kelibsiz",
        subtitle = "PIN-kodni kiriting",
        icon = Icons.Rounded.Lock,
        error = error, shakeKey = shake,
        enabled = locked == 0 && !checking,
        bioIcon = bio, onBio = { askBio() },
        footer = {
            Txt("PIN-kodni unutdim", Modifier.press {
                Sheets.confirm(
                    "PIN-kodni unutdingizmi?",
                    "Xavfsizlik uçun hisobdan çiqasiz. Keyin login va parol bilan qayta kirib, yangi PIN-kod örnatasiz. Ma'lumotlaringiz yöqolmaydi.",
                    ok = "Hisobdan çiqiş", danger = true,
                ) { scope.launch { signOut(ctx) } }
            }.padding(10.dp), 14.5.sp, FontWeight.SemiBold, pal.a1)
        },
    ) { code ->
        checking = true
        scope.launch {
            val r = withContext(Dispatchers.Default) { Pin.check(code) }
            checking = false
            when (r) {
                Pin.Result.Ok -> { error = null; onUnlock() }
                is Pin.Result.Wrong -> { error = "PIN notöğri. Yana ${r.left} ta uriniş qoldi"; shake++ }
                is Pin.Result.Locked -> { shake++; locked = r.seconds }
                Pin.Result.Wipe -> {
                    signOut(ctx)
                    Toasts.show("PIN köp marta notöğri terildi. Xavfsizlik uçun hisobdan çiqildi", "err")
                }
            }
        }
    }
}
