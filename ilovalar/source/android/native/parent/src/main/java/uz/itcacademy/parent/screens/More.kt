package uz.itcacademy.parent.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.fragment.app.FragmentActivity
import kotlinx.coroutines.launch
import org.json.JSONObject
import uz.itcacademy.parent.*
import uz.itcacademy.parent.ui.*

private class Tile(val icon: ImageVector, val title: String, val sub: String, val color: @Composable () -> Color, val badge: Int = 0, val go: () -> Unit)

@Composable
fun MoreScreen() {
    val p = pal
    val parent = AppState.parent
    val tiles = listOf(
        Tile(Icons.Rounded.FamilyRestroom, "Farzandlarim", "${AppState.children.size} ta farzand", { p.a1 }) { AppState.open(Route.Children) },
        Tile(Icons.Rounded.EmojiEvents, "Yutuqlar", "Nişon va sertifikatlar", { p.amber }) { AppState.open(Route.Achievements) },
        Tile(Icons.Rounded.Forum, "Xabarlar", "Öquv markazi bilan", { p.blue }, AppState.unreadReplies) { AppState.open(Route.Messages) },
        Tile(Icons.Rounded.Notifications, "Bildirişnomalar", "Barça voqealar", { p.a2 }, AppState.unreadNotif) { AppState.open(Route.Notifications) },
        Tile(Icons.Rounded.LocalLibrary, "Kitoblar", "Kutubxona ijarasi", { p.green }) { AppState.open(Route.Books) },
        Tile(Icons.Rounded.HelpOutline, "Qöllanma", "Qayerda nima bor", { p.blue }) { AppState.open(Route.Help) },
    )
    Page {
        H1("Yana")
        // Profil kartasi
        Row(
            Modifier.reveal(0).fillMaxWidth().card().press { AppState.open(Route.Profile) }.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Avatar(null, parent?.str("full_name"), 54.dp)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Txt(parent?.str("full_name").orEmpty(), size = 17.sp, weight = FontWeight.Bold, translate = false)
                Muted(parent?.str("phone").orEmpty(), translate = false)
            }
            Icon(Icons.Rounded.ChevronRight, null, Modifier.size(22.dp), p.muted)
        }
        tiles.chunked(2).forEachIndexed { r, row ->
            Row(Modifier.reveal(r + 1), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                row.forEach { t ->
                    Box(Modifier.weight(1f)) {
                        Column(Modifier.fillMaxWidth().card().press(onClick = t.go).padding(16.dp)) {
                            IcoBox(t.icon, t.color(), 44.dp)
                            Spacer(Modifier.height(12.dp))
                            Txt(t.title, size = 15.sp, weight = FontWeight.SemiBold, lines = 1)
                            Muted(t.sub, lines = 1)
                        }
                        if (t.badge > 0) Box(
                            Modifier.align(Alignment.TopEnd).padding(12.dp).size(22.dp).clip(CircleShape).background(p.red),
                            contentAlignment = Alignment.Center,
                        ) { Txt(if (t.badge > 9) "9+" else "${t.badge}", size = 11.sp, weight = FontWeight.Bold, color = Color.White) }
                    }
                }
                if (row.size == 1) Spacer(Modifier.weight(1f))
            }
        }
        GlassCard(Modifier.reveal(5), pad = 6.dp) {
            MenuRow(Icons.Rounded.Tune, "Sozlamalar", "Mavzu, rang, matn ölçami, bildirişnomalar") { AppState.open(Route.SettingsPage) }
            Hairline()
            MenuRow(Icons.Rounded.Shield, "Xavfsizlik", "PIN-kod, barmoq izi, parol") { AppState.open(Route.Security) }
        }
        Muted("ITC Ota Ona ${BuildConfig.VERSION_NAME} · IT Creative Academy", Modifier.fillMaxWidth().padding(top = 4.dp), 12.sp)
    }
}

@Composable
fun MenuRow(icon: ImageVector, title: String, sub: String = "", color: Color = pal.text2, trailing: (@Composable () -> Unit)? = null, onClick: (() -> Unit)? = null) {
    Row2(title, sub, Modifier.padding(horizontal = 10.dp),
        leading = { Tinted(pal.surface2, Modifier.size(38.dp)) { Icon(icon, null, Modifier.size(20.dp), color) } },
        trailing = trailing ?: if (onClick != null) ({ Icon(Icons.Rounded.ChevronRight, null, Modifier.size(20.dp), pal.muted) }) else null,
        onClick = onClick)
}

// ───────── Farzandlar ─────────
@Composable
fun ChildrenScreen() {
    val p = pal
    Page {
        BackHeader("Farzandlarim", onBack = { AppState.back() })
        if (AppState.children.isEmpty()) NoChild()
        AppState.children.forEachIndexed { i, c ->
            val on = c.int("id") == AppState.child?.int("id")
            GlassCard(Modifier.reveal(i).press { AppState.selectChild(c.int("id")); AppState.switchTab("home") }) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Avatar(c.strOrNull("photo"), c.str("name"), 52.dp, if (on) p.a1 else null)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Txt(c.str("name"), size = 16.sp, weight = FontWeight.Bold, translate = false)
                        Muted(c.strings("courses").joinToString(" · ").ifEmpty { "Kursga yozilmagan" }, lines = 2, translate = false)
                    }
                    if (on) TagAccent("Tanlangan", Icons.Rounded.Check)
                }
                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    ChildMetric("${c.int("progress")}%", "Özlaştiriş", p.a1, Modifier.weight(1f))
                    ChildMetric("${num(c.dbl("test_avg"))}%", "Testlar", scoreColor(c.dbl("test_avg")), Modifier.weight(1f))
                    ChildMetric("${c.int("attendance")}%", c.str("attendance_label"), scoreColor(c.int("attendance")), Modifier.weight(1f))
                }
                Spacer(Modifier.height(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CoinDot(16.dp); Spacer(Modifier.width(5.dp)); Muted("${num(c.int("coins"))} coin")
                    Spacer(Modifier.width(14.dp))
                    Icon(Icons.Rounded.LocalFireDepartment, null, Modifier.size(16.dp), p.amber); Spacer(Modifier.width(4.dp)); Muted("${c.int("streak")} kun ketma-ket")
                    Spacer(Modifier.weight(1f))
                    c.strOrNull("last_activity")?.let { Muted(ago(it), size = 11.5.sp) }
                }
            }
        }
    }
}

@Composable
private fun ChildMetric(value: String, label: String, color: Color, modifier: Modifier) {
    Column(modifier.clip(RoundedCornerShape(14.dp)).background(pal.surface).padding(vertical = 9.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Txt(value, size = 16.sp, weight = FontWeight.Bold, color = color, translate = false)
        Muted(label, size = 11.sp, lines = 1)
    }
}

// ───────── Profil ─────────
@Composable
fun ProfileScreen() {
    val parent = AppState.parent ?: JSONObject()
    Page {
        BackHeader("Profil", onBack = { AppState.back() })
        Column(Modifier.reveal(0).fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
            Avatar(null, parent.str("full_name"), 92.dp, pal.a1)
            Spacer(Modifier.height(12.dp))
            Txt(parent.str("full_name"), size = 22.sp, weight = FontWeight.Bold, translate = false)
            Muted("Ota-ona hisobi")
        }
        GlassCard(Modifier.reveal(1), pad = 6.dp) {
            MenuRow(Icons.Rounded.Phone, parent.str("phone"), "Telefon raqam")
            Hairline()
            MenuRow(Icons.Rounded.AlternateEmail, parent.str("email").ifEmpty { "Kiritilmagan" }, "Email")
            Hairline()
            MenuRow(Icons.Rounded.Badge, parent.str("username"), "Login")
        }
        GlassCard(Modifier.reveal(2), pad = 6.dp) {
            MenuRow(Icons.Rounded.Edit, "Ma'lumotlarni tahrirlaş") { AppState.open(Route.EditProfile) }
            Hairline()
            MenuRow(Icons.Rounded.Password, "Parolni özgartiriş") { AppState.open(Route.Password) }
        }
        LogoutButton(Modifier.reveal(3))
    }
}

@Composable
fun LogoutButton(modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    Btn("Hisobdan çiqiş", modifier.fillMaxWidth(), BtnKind.Danger, Icons.Rounded.Logout) {
        Sheets.confirm("Hisobdan çiqasizmi?", "Qayta kiriş uçun login va parol kerak böladi. PIN-kod ham qaytadan örnatiladi.", "Çiqiş", danger = true) {
            scope.launch { signOut(ctx) }
        }
    }
}

@Composable
fun EditProfileScreen() {
    val parent = AppState.parent ?: JSONObject()
    val scope = rememberCoroutineScope()
    var first by remember { mutableStateOf(parent.str("first_name")) }
    var last by remember { mutableStateOf(parent.str("last_name")) }
    var phone by remember { mutableStateOf(parent.str("phone")) }
    var email by remember { mutableStateOf(parent.str("email")) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    Page {
        BackHeader("Tahrirlaş", onBack = { AppState.back() })
        GlassCard(Modifier.reveal(0)) {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Field(first, { first = it }, "Ism", icon = Icons.Rounded.Person)
                Field(last, { last = it }, "Familiya", icon = Icons.Rounded.Person)
                Field(phone, { phone = it }, "Telefon raqam", icon = Icons.Rounded.Phone, keyboard = KeyboardType.Phone)
                Field(email, { email = it }, "Email (ixtiyoriy)", icon = Icons.Rounded.AlternateEmail, keyboard = KeyboardType.Email)
                if (error != null) Txt(error!!, size = 13.5.sp, color = pal.red)
                Btn("Saqlaş", Modifier.fillMaxWidth(), BtnKind.Primary, Icons.Rounded.Check, busy = busy) {
                    error = null
                    busy = true
                    scope.launch {
                        try {
                            Api.patch("me/", JSONObject().put("first_name", first).put("last_name", last).put("phone", phone).put("email", email))
                            AppState.refresh()
                            Toasts.show("Saqlandi")
                            AppState.back()
                        } catch (e: ApiError) { error = e.message }
                        busy = false
                    }
                }
            }
        }
    }
}

@Composable
fun PasswordScreen() {
    val scope = rememberCoroutineScope()
    var cur by remember { mutableStateOf("") }
    var p1 by remember { mutableStateOf("") }
    var p2 by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    Page {
        BackHeader("Parolni özgartiriş", onBack = { AppState.back() })
        GlassCard(Modifier.reveal(0)) {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Muted("Parol özgargaç, boşqa telefonlardagi kirişlar avtomatik bekor qilinadi.", size = 13.5.sp)
                Field(cur, { cur = it }, "Joriy parol", icon = Icons.Rounded.Lock, password = true)
                Field(p1, { p1 = it }, "Yangi parol", icon = Icons.Rounded.Key, password = true)
                Field(p2, { p2 = it }, "Yangi parolni takrorlang", icon = Icons.Rounded.Key, password = true)
                PasswordHints(p1)
                if (error != null) Txt(error!!, size = 13.5.sp, color = pal.red)
                Btn("Özgartiriş", Modifier.fillMaxWidth(), BtnKind.Primary, Icons.Rounded.Check, busy = busy) {
                    error = null
                    busy = true
                    scope.launch {
                        try {
                            Api.post("me/password/", JSONObject().put("current_password", cur).put("new_password", p1).put("confirm_password", p2))
                            Toasts.show("Parol özgartirildi")
                            AppState.back()
                        } catch (e: ApiError) { error = e.message }
                        busy = false
                    }
                }
            }
        }
    }
}

/** Parol talablari jonli tekshiriladi. */
@Composable
private fun PasswordHints(pw: String) {
    val rules = listOf(
        "Kamida 8 ta belgi" to (pw.length >= 8),
        "Faqat raqamlardan iborat emas" to (pw.isNotEmpty() && !pw.all { it.isDigit() }),
        "Harf va raqam aralaş" to (pw.any { it.isLetter() } && pw.any { it.isDigit() }),
    )
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        rules.forEach { (t, ok) ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(if (ok) Icons.Rounded.CheckCircle else Icons.Rounded.RadioButtonUnchecked, null, Modifier.size(16.dp), if (ok) pal.green else pal.muted)
                Spacer(Modifier.width(6.dp))
                Muted(t, size = 12.5.sp)
            }
        }
    }
}

// ───────── Sozlamalar ─────────
@Composable
fun SettingsScreen() {
    val p = pal
    val ctx = LocalContext.current
    Page {
        BackHeader("Sozlamalar", onBack = { AppState.back() })
        SectionTitle("Köriniş", Icons.Rounded.Palette)
        GlassCard(Modifier.reveal(0)) {
            Muted("Mavzu")
            Spacer(Modifier.height(8.dp))
            Segmented(listOf("Qorong'i", "Yorug'", "Tizim"), listOf("dark", "light", "system").indexOf(Settings.theme).coerceAtLeast(0)) { i ->
                Settings.update { theme = listOf("dark", "light", "system")[i] }
            }
            Spacer(Modifier.height(16.dp))
            Muted("Asosiy rang")
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                listOf("violet" to Color(0xFF8B5CF6), "ocean" to Color(0xFF3B82F6), "emerald" to Color(0xFF10B981), "sunset" to Color(0xFFF97316)).forEach { (k, c) ->
                    val on = Settings.accent == k
                    val s by animateFloatAsState(if (on) 1.1f else 1f, label = "acc")
                    Box(
                        Modifier.graphicsLayer { scaleX = s; scaleY = s }.size(44.dp).clip(CircleShape).background(c)
                            .then(if (on) Modifier.border(3.dp, p.text, CircleShape) else Modifier)
                            .press { Settings.update { accent = k } },
                        contentAlignment = Alignment.Center,
                    ) { if (on) Icon(Icons.Rounded.Check, null, Modifier.size(22.dp), Color.White) }
                }
            }
        }
        GlassCard(Modifier.reveal(1), pad = 6.dp) {
            MenuRow(Icons.Rounded.TextFields, "Katta matn", "Barça yozuvlar kattaroq", trailing = { Switch(Settings.largeText) { v -> Settings.update { largeText = v } } })
            Hairline()
            MenuRow(Icons.Rounded.Animation, "Animatsiyalar", "Öçirilsa ilova tezroq va sokinroq", trailing = { Switch(Settings.motion) { v -> Settings.update { motion = v } } })
        }
        SectionTitle("Bildirişnomalar", Icons.Rounded.Notifications)
        GlassCard(Modifier.reveal(2), pad = 6.dp) {
            MenuRow(Icons.Rounded.NotificationsActive, "Bildirişnomalar", "Natija, baho, davomat, tölov, xabar", trailing = {
                Switch(Settings.notify) { v ->
                    Settings.update { notify = v }
                    if (v && !Notify.allowed(ctx)) (ctx as? FragmentActivity)?.let {
                        Settings.askedNotify = false
                        askNotifications(it)
                    }
                }
            })
            if (Settings.notify && !Notify.allowed(ctx)) {
                Hairline()
                MenuRow(Icons.Rounded.WarningAmber, "Telefonda ruxsat berilmagan", "Bosing va ilova sozlamalarida bildirişnomalarga ruxsat bering", p.amber) {
                    val i = android.content.Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS, android.net.Uri.parse("package:${ctx.packageName}"))
                    runCatching { ctx.startActivity(i) }
                }
            }
        }
    }
}

// ───────── Xavfsizlik ─────────
@Composable
fun SecurityScreen() {
    val ctx = LocalContext.current
    val act = ctx as FragmentActivity
    val scope = rememberCoroutineScope()
    var changing by remember { mutableStateOf(false) }
    var verified by remember { mutableStateOf(false) }
    var bio by remember { mutableStateOf(Pin.biometric) }
    if (changing) {
        if (!verified) {
            // Avval joriy PIN tasdiqlanadi
            var error by remember { mutableStateOf<String?>(null) }
            var shake by remember { mutableIntStateOf(0) }
            androidx.activity.compose.BackHandler { changing = false }
            PinPad("Joriy PIN-kod", "Özgartiriş uçun avval joriy kodni kiriting", Icons.Rounded.Lock, error, shake) { code ->
                when (val r = Pin.check(code)) {
                    Pin.Result.Ok -> verified = true
                    is Pin.Result.Wrong -> { error = "PIN notöğri. Yana ${r.left} ta uriniş"; shake++ }
                    is Pin.Result.Locked -> { error = "${r.seconds} soniya kuting"; shake++ }
                    Pin.Result.Wipe -> scope.launch { signOut(ctx) }
                }
            }
        } else {
            androidx.activity.compose.BackHandler { changing = false; verified = false }
            SetPinScreen(onDone = { changing = false; verified = false }, changing = true)
        }
        return
    }
    Page {
        BackHeader("Xavfsizlik", onBack = { AppState.back() })
        GlassCard(Modifier.reveal(0)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IcoBox(Icons.Rounded.VerifiedUser, pal.green, 46.dp)
                Spacer(Modifier.width(12.dp))
                Column {
                    Txt("Hisobingiz himoyalangan", weight = FontWeight.Bold)
                    Muted("PIN-kod, shifrlangan xotira, ekran rasmi taqiqlangan")
                }
            }
        }
        GlassCard(Modifier.reveal(1), pad = 6.dp) {
            MenuRow(Icons.Rounded.Pin, "PIN-kodni özgartiriş") { changing = true }
            if (Bio.available(act)) {
                Hairline()
                MenuRow(Icons.Rounded.Fingerprint, "Barmoq izi bilan oçiş", "Yuz yoki barmoq izi orqali tez kiriş", trailing = {
                    Switch(bio) { v ->
                        if (v) Bio.prompt(act, "Barmoq izini tasdiqlang", onOk = { Pin.biometric = true; bio = true; Toasts.show("Barmoq izi yoqildi") })
                        else { Pin.biometric = false; bio = false }
                    }
                })
            }
            Hairline()
            MenuRow(Icons.Rounded.Password, "Hisob parolini özgartiriş") { AppState.open(Route.Password) }
        }
        GlassCard(Modifier.reveal(2)) {
            SectionTitle("Qanday himoyalangan", Icons.Rounded.Shield)
            listOf(
                Icons.Rounded.Lock to "Ilova har oçilganda va 30 soniyadan köp fonda turgandan keyin PIN-kod söraydi",
                Icons.Rounded.GppMaybe to "5 marta xato PIN — kutiş vaqti, 10 marta — hisobdan avtomatik çiqiş",
                Icons.Rounded.EnhancedEncryption to "Kiriş kaliti telefonda shifrlangan, serverda faqat uning izi saqlanadi",
                Icons.Rounded.ScreenLockPortrait to "Ekran rasmi olinmaydi, söngi ilovalar oynasida ma'lumot körinmaydi",
                Icons.Rounded.NoEncryption to "Bildirişnoma qulflangan ekranda tafsilotsiz körsatiladi",
                Icons.Rounded.DevicesOther to "Parol özgarsa, boşqa telefonlardagi kirişlar bekor böladi",
            ).forEach { (ic, tx) ->
                Row(Modifier.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(ic, null, Modifier.size(20.dp), pal.a1)
                    Spacer(Modifier.width(12.dp))
                    Txt(tx, size = 13.5.sp, color = pal.text2)
                }
            }
        }
        LogoutButton(Modifier.reveal(3))
    }
}

// ───────── Qo'llanma ─────────
@Composable
fun HelpScreen() {
    val faq = listOf(
        "Farzandimni qanday almaştiraman?" to "Har bir bölim tepasida farzandlar ismi turadi. Kerakli ismni bosing — sahifa şu farzand böyiça yangilanadi. Barça farzandlar \"Yana → Farzandlarim\" böliminda.",
        "Test natijasini qayerdan köraman?" to "Pastdagi \"Öqiş\" tugmasi → \"Testlar\". Har bir test bali, töğri javoblar soni va sanasi körsatiladi.",
        "Uy vazifasi baholandimi?" to "\"Öqiş\" → \"Vazifalar\". Baho va ustoz izohi vazifa kartasida chiqadi. Baholanganda bildirişnoma ham keladi.",
        "Farzandim darsga keldimi?" to "\"Davomat\" bölimidagi kalendarda har bir kun rangda: yaşil — kelgan, sariq — keçikkan, qizil — kelmagan.",
        "Tölovni qanday qilaman?" to "\"Tölov\" bölimi → \"Onlayn tölaş\". Xavfsiz tölov sahifasi brauzerda oçiladi. Tölov tasdiqlangaç balans yangilanadi.",
        "Ustoz bilan qanday bog'lanaman?" to "\"Yana → Xabarlar\". Mavzuni tanlab xabar yozing — öquv markazi javobi şu yerga keladi va bildirişnoma bilan xabar qilinadi.",
        "PIN-kodni unutsam-çi?" to "Qulf ekranidagi \"PIN-kodni unutdim\" tugmasini bosing. Hisobdan çiqasiz, keyin login va parol bilan kirib yangi PIN örnatasiz.",
        "Bildirişnomalar kelmayapti" to "\"Yana → Sozlamalar\"da bildirişnomalar yoqilganini va telefonda ilovaga ruxsat berilganini tekşiring. Ilova har 15 daqiqada yangiliklarni tekşiradi.",
    )
    Page {
        BackHeader("Qöllanma", onBack = { AppState.back() })
        Btn("Tanişuv qöllanmasini qayta körish", Modifier.reveal(0).fillMaxWidth(), BtnKind.Primary, Icons.Rounded.PlayCircle) {
            AppState.switchTab("home")
            Settings.tourDone = false
        }
        SectionTitle("Köp beriladigan savollar", Icons.Rounded.QuestionAnswer)
        faq.forEachIndexed { i, (q, a) -> FaqItem(q, a, Modifier.reveal(i + 1)) }
    }
}

@Composable
private fun FaqItem(q: String, a: String, modifier: Modifier) {
    var open by remember { mutableStateOf(false) }
    val rot by animateFloatAsState(if (open) 180f else 0f, label = "faq")
    Column(modifier.fillMaxWidth().card(RoundedCornerShape(18.dp)).press(scale = .99f) { open = !open }.padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Txt(q, Modifier.weight(1f), 15.sp, FontWeight.SemiBold)
            Icon(Icons.Rounded.ExpandMore, null, Modifier.size(22.dp).graphicsLayer { rotationZ = rot }, pal.muted)
        }
        AnimatedVisibility(open, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
            Txt(a, Modifier.padding(top = 8.dp), 14.sp, color = pal.text2)
        }
    }
}
