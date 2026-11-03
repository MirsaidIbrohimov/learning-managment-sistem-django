package uz.itcacademy.lms.screens

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
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import uz.itcacademy.lms.*
import uz.itcacademy.lms.ui.*

/** Sayt sahifasini tizim brauzerida ochadi, qayta login so'ramaydi. WebView emas. */
@Composable
fun OpenSiteButton(label: String, path: String) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    Btn(label, small = true, icon = Icons.Rounded.OpenInNew, busy = busy) {
        busy = true
        scope.launch { openBrowser(ctx, Api.webUrl(path)); busy = false }
    }
}

private val GENDER = mapOf("male" to "Erkak", "female" to "Ayol", "M" to "Erkak", "F" to "Ayol")

@Composable
fun ProfileScreen() {
    val u = AppState.user ?: return
    val scope = rememberCoroutineScope()
    var bio by remember { mutableStateOf(u.str("bio")) }
    var saving by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { AppState.refreshUser() }
    val name = u.str("full_name").ifEmpty { u.str("username") }
    val pct = u.int("profile_completion_percent")
    val ach = rememberLoad {
        suspend fun <T> a(b: suspend () -> T): T? = try { b() } catch (_: ApiError) { null }
        Ach(
            a { Api.getAll("/api/v1/my/test-results/", max = 5) }, a { Api.getAll("/api/v1/my/certificates/", max = 2) },
            a { Api.get("/api/v1/reyting/", mapOf("tab" to "coins", "limit" to 1)) }, a { Api.getAny("/api/v1/my/enrollments/") },
        )
    }

    Page(bottom = 40.dp) {
        BackHeader("Profil", onBack = { AppState.back() }) {
            Tinted(pal.surface2, Modifier.size(40.dp).press { AppState.open(Route.SettingsPage) }, CircleShape) {
                Icon(Icons.Rounded.Settings, t("Sozlamalar"), Modifier.size(21.dp), pal.text)
            }
        }
        Column(Modifier.reveal(0).fillMaxWidth().card(), horizontalAlignment = Alignment.CenterHorizontally) {
            Box(Modifier.fillMaxWidth().height(74.dp).background(Brush.linearGradient(listOf(pal.a1.copy(alpha = .55f), pal.a3.copy(alpha = .4f)))))
            Box(Modifier.offset(y = (-44).dp)) { Avatar(u.strOrNull("photo"), name, 88.dp, pal.a1) }
            Column(Modifier.offset(y = (-36).dp).padding(horizontal = 16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Txt(name, size = 22.sp, weight = FontWeight.Bold, translate = false, align = TextAlign.Center)
                    if (u.bool("is_premium")) { Spacer(Modifier.width(8.dp)); TagPremium() }
                }
                Muted("@${u.str("username")} · ${dateText(u.str("date_joined"))} ${t("dan beri a'zo")}", translate = false)
                Spacer(Modifier.height(10.dp))
                OpenSiteButton("Saytda tahrirlaş", "/profile/edit/")
            }
        }

        val d = ach.data
        val rank = d?.rank?.int("user_rank") ?: 0
        Row(Modifier.reveal(1), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            MiniStat(num(u.int("coins")), "Coin", Modifier.weight(1f))
            MiniStat(if (rank > 0) "#${num(rank)}" else "—", "Reyting", Modifier.weight(1f))
            MiniStat(d?.tests?.count { it.bool("passed") }?.let { num(it) } ?: "—", "Ötilgan testlar", Modifier.weight(1f))
            MiniStat(d?.certs?.size?.let { num(it) } ?: "—", "Sertifikatlar", Modifier.weight(1f))
        }

        if (d != null) Badges(u, d, Modifier.reveal(2))

        GlassCard(Modifier.reveal(3).fillMaxWidth()) {
            SectionTitle("Profil töliqligi", Icons.Rounded.TrackChanges)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Ring(pct, 72.dp, textSize = 15.sp)
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) {
                    Muted(if (pct >= 100) "Profilingiz töliq to'ldirilgan. Ajoyib!" else "Barça imkoniyatlardan foydalaniş uçun profilni töliq töldiring.")
                    if (pct < 100) { Spacer(Modifier.height(8.dp)); OpenSiteButton("Töldiriş", "/profile/complete/") }
                }
            }
        }

        GlassCard(Modifier.reveal(4).fillMaxWidth()) {
            SectionTitle("Şaxsiy ma'lumotlar", Icons.Rounded.Person)
            Info("Ism", u.str("first_name")); Info("Familiya", u.str("last_name"))
            Info("Tuğilgan sana", u.strOrNull("birth_date")?.let { dateText(it) }.orEmpty())
            Info("Jinsi", GENDER[u.str("gender")]?.let { t(it) } ?: u.str("gender"))
            Info("Millati", u.str("nationality"))
            Info("Maktab", listOf(u.str("school_name"), u.strOrNull("school_number")?.let { "$it-${t("maktab")}" }.orEmpty()).filter { it.isNotEmpty() }.joinToString(", "))
            Info("Manzil", u.str("address"))
        }

        GlassCard(Modifier.reveal(5).fillMaxWidth()) {
            SectionTitle("Men haqimda", Icons.Rounded.ChatBubbleOutline)
            Field(bio, { if (it.length <= 500) bio = it }, "Özingiz haqingizda qisqaça yozing…", single = false, minHeight = 92.dp)
            Spacer(Modifier.height(10.dp))
            Btn("Saqlaş", Modifier.align(Alignment.End), BtnKind.Primary, Icons.Rounded.Check, busy = saving, small = true) {
                saving = true
                scope.launch {
                    try {
                        AppState.user = Api.patch("/api/v1/profile/", JSONObject().put("bio", bio.trim()))
                        Toasts.show("Saqlandi")
                    } catch (e: ApiError) { Toasts.show(e.message.orEmpty(), "err") }
                    saving = false
                }
            }
        }
    }
}

private class Ach(val tests: List<JSONObject>?, val certs: List<JSONObject>?, val rank: JSONObject?, val enr: Any?)

@Composable
private fun Info(k: String, v: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Muted(k, Modifier.width(120.dp), 13.5.sp)
        Txt(v.ifEmpty { "—" }, Modifier.weight(1f), weight = FontWeight.Medium, translate = false)
    }
}

@Composable
private fun Badges(u: JSONObject, d: Ach, modifier: Modifier) {
    val tests = d.tests.orEmpty()
    val passed = tests.count { it.bool("passed") }
    val perfect = tests.count { it.int("total_questions") > 0 && it.int("correct_answers") == it.int("total_questions") }
    val r = d.rank?.int("user_rank") ?: 0
    val courses = (d.enr as? JSONObject)?.optInt("count", Api.rows(d.enr).size) ?: Api.rows(d.enr).size
    val days = parseDate(u.str("date_joined"))?.let { ((System.currentTimeMillis() - it.time) / 86_400_000L).toInt() } ?: 0
    val coins = u.int("coins")
    val list = listOf(
        Badge(Icons.Rounded.PlayArrow, "Ilk qadam", "Kursga yoziling", courses, 1),
        Badge(Icons.Rounded.TaskAlt, "Birinçi test", "1 ta testdan öting", passed, 1),
        Badge(Icons.Rounded.LocalFireDepartment, "Test ustasi", "10 ta testdan öting", passed, 10),
        Badge(Icons.Rounded.TrackChanges, "Mukammal", "Testda 100% natija", perfect, 1),
        Badge(Icons.Rounded.AccountBalanceWallet, "Coin yiğuvçi", "1 000 coin töplang", coins, 1000),
        Badge(Icons.Rounded.CardGiftcard, "Boy öquvçi", "10 000 coin töplang", coins, 10000),
        Badge(Icons.Rounded.EmojiEvents, "Top 10", "Reytingda top 10 ga kiring", if (r in 1..10) 1 else 0, 1),
        Badge(Icons.Rounded.WorkspacePremium, "Sertifikat egasi", "Birinçi sertifikat", d.certs?.size ?: 0, 1),
        Badge(Icons.Rounded.Star, "Premium", "Premium a'zo böling", if (u.bool("is_premium")) 1 else 0, 1),
        Badge(Icons.Rounded.CalendarMonth, "Sodiq öquvçi", "1 yildan beri platformada", days, 365),
    )
    GlassCard(modifier.fillMaxWidth()) {
        SectionTitle("${t("Nişonlar")} — ${list.count { it.cur >= it.goal }} / ${list.size}", Icons.Rounded.AutoAwesome)
        list.chunked(2).forEach { pair ->
            Row(Modifier.padding(bottom = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                pair.forEach { b -> BadgeTile(b, Modifier.weight(1f)) }
            }
        }
    }
}

private class Badge(val icon: ImageVector, val name: String, val desc: String, val cur: Int, val goal: Int)

@Composable
private fun BadgeTile(b: Badge, modifier: Modifier) {
    val done = b.cur >= b.goal
    Column(
        modifier.card(RoundedCornerShape(18.dp), if (done) pal.a1.copy(alpha = .14f) else null).padding(12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(
                if (done) Brush.linearGradient(listOf(Color(0xFFFBBF24), Color(0xFFF97316))) else Brush.linearGradient(listOf(pal.surface2, pal.surface2)),
            ),
            contentAlignment = Alignment.Center,
        ) { Icon(if (done) b.icon else Icons.Rounded.Lock, null, Modifier.size(22.dp), if (done) Color.White else pal.muted) }
        Spacer(Modifier.height(7.dp))
        Txt(b.name, size = 13.sp, weight = FontWeight.SemiBold, lines = 1)
        Spacer(Modifier.height(4.dp))
        if (done) Txt("Oçildi", size = 11.5.sp, color = pal.green, weight = FontWeight.SemiBold)
        else {
            ProgressBar(b.cur.toFloat() / b.goal, height = 4.dp, modifier = Modifier.fillMaxWidth(.85f))
            Muted(if (b.goal > 1) "${num(b.cur.coerceAtMost(b.goal))} / ${num(b.goal)}" else b.desc, Modifier.padding(top = 3.dp), 11.sp, 1, translate = b.goal == 1)
        }
    }
}

@Composable
fun SettingsScreen(onLogout: () -> Unit) {
    val ctx = LocalContext.current
    Page(bottom = 40.dp) {
        BackHeader("Sozlamalar", "Ilova körinişi va hisob", { AppState.back() })

        GlassCard(Modifier.reveal(0).fillMaxWidth()) {
            Txt("Til", weight = FontWeight.SemiBold)
            Muted("Interfeys tili: o'zbekça, ruşça yoki inglizça")
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                I18n.LANGS.forEach { (k, name) ->
                    val on = Settings.lang == k
                    val shape = RoundedCornerShape(18.dp)
                    Column(
                        Modifier.weight(1f).press { Settings.update { lang = k } }
                            .clip(shape).background(if (on) pal.a1.copy(alpha = .15f) else pal.surface)
                            .border(1.5.dp, if (on) pal.a1 else pal.border, shape).padding(vertical = 14.dp, horizontal = 4.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Flag(k, Modifier.size(48.dp, 32.dp))
                        Spacer(Modifier.height(8.dp))
                        Txt(name, size = 12.5.sp, weight = FontWeight.SemiBold, lines = 1, translate = false)
                    }
                }
            }
        }

        GlassCard(Modifier.reveal(1).fillMaxWidth()) {
            Txt("Mavzu", weight = FontWeight.SemiBold)
            Muted("Tungi, kunduzgi yoki telefon sozlamasiga mos")
            Spacer(Modifier.height(10.dp))
            Segmented(listOf("Tungi", "Kunduzgi", "Tizim"), listOf("dark", "light", "system").indexOf(Settings.theme).coerceAtLeast(0)) { i ->
                Settings.update { theme = listOf("dark", "light", "system")[i] }
            }
            Spacer(Modifier.height(16.dp))
            Txt("Urğu rangi", weight = FontWeight.SemiBold)
            Muted("Tugmalar, belgilar va grafikalar rangi")
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                listOf(
                    "violet" to listOf(Color(0xFF8B5CF6), Color(0xFFEC4899)), "ocean" to listOf(Color(0xFF3B82F6), Color(0xFF22D3EE)),
                    "emerald" to listOf(Color(0xFF10B981), Color(0xFF84CC16)), "sunset" to listOf(Color(0xFFF97316), Color(0xFFEC4899)),
                ).forEach { (k, colors) ->
                    Box(
                        Modifier.size(40.dp).press(scale = .88f) { Settings.update { accent = k } }
                            .then(if (Settings.accent == k) Modifier.border(2.dp, pal.text, CircleShape).padding(4.dp) else Modifier)
                            .clip(CircleShape).background(Brush.linearGradient(colors)),
                    )
                }
            }
        }

        GlassCard(Modifier.reveal(2).fillMaxWidth(), 14.dp) {
            SwitchRow("Animatsiyalar", "Sahifa ötişlari va harakatlar", Settings.motion) { v -> Settings.update { motion = v } }
            Hairline()
            SwitchRow("Oçiliş ovozi", "Ilova oçilganda qisqa ovoz", Settings.sound) { v -> Settings.update { sound = v } }
            Hairline()
            SwitchRow("Coin tuşganda xabar beriş", "Balans köpaysa ekranda qisqa xabar çiqadi", Settings.coinToast) { v -> Settings.update { coinToast = v } }
            Hairline()
            Row2("Oçilgan darslar tarixi", "\"Davom ettiriş\" va ✓ belgilari faqat şu telefonda saqlanadi", trailing = {
                Btn("Tozalaş", small = true) {
                    Sheets.confirm("Tarixni tozalaş", "Yaqinda oçilgan darslar va ✓ belgilari öçiriladi. Serverdagi natijalaringizga ta'sir qilmaydi.", "Tozalaş", true) {
                        Settings.clearHistory(); Toasts.show("Tarix tozalandi")
                    }
                }
            })
        }

        GlassCard(Modifier.reveal(3).fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Tinted(Color.White, Modifier.size(52.dp), RoundedCornerShape(14.dp)) {
                    androidx.compose.foundation.Image(androidx.compose.ui.res.painterResource(uz.itcacademy.lms.R.mipmap.ic_launcher), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                }
                Spacer(Modifier.width(12.dp))
                Column {
                    Txt("ITC Academy", weight = FontWeight.Bold, translate = false)
                    Muted("${t("Versiya")} ${BuildConfig.VERSION_NAME} · © IT Creative Academy", translate = false)
                }
            }
            Spacer(Modifier.height(14.dp))
            Btn("Hisobdan çiqiş", Modifier.fillMaxWidth(), BtnKind.Danger, Icons.Rounded.Logout) {
                Sheets.confirm("Hisobdan çiqiş", "Ilovadan çiqmoqçimisiz? Keyingi safar login va parolni qayta kiritasiz.", "Çiqiş", true, onLogout)
            }
        }
    }
}

@Composable
private fun SwitchRow(title: String, sub: String, on: Boolean, onChange: (Boolean) -> Unit) {
    Row2(title, sub, trailing = { Switch(on, onChange) })
}

// ───────── Kutubxona ─────────
@Composable
fun LibraryScreen() {
    var tab by remember { mutableIntStateOf(0) }
    Page(bottom = 40.dp) {
        BackHeader("Kutubxona", "Kitoblarni qidiring va ijaraga oliş uçun ariza qoldiring", { AppState.back() })
        Segmented(listOf("Kitoblar", "Arizalarim", "Ijaralarim"), tab) { tab = it }
        when (tab) { 0 -> BooksTab(); 1 -> RequestsTab(); else -> RentalsTab() }
    }
}

@Composable
private fun BooksTab() {
    var q by remember { mutableStateOf("") }
    var query by remember { mutableStateOf("") }
    var sort by remember { mutableStateOf("title") }
    var avail by remember { mutableStateOf(false) }
    LaunchedEffect(q) { delay(350); query = q.trim() }
    val load = rememberLoad(query, sort, avail) {
        Api.rows(Api.getAny("/api/v1/library/books/", mapOf("search" to query, "sort" to sort, "available" to if (avail) "1" else "")))
    }
    Field(q, { q = it }, "Nomi, muallifi yoki ISBN", icon = Icons.Rounded.Search)
    Chips(listOf("title" to "Nomi (A–Z)", "newest" to "Eng yangilari", "author" to "Muallif", "available" to "Mavjudlari avval"), sort) { sort = it }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Switch(avail) { avail = it }; Spacer(Modifier.width(10.dp)); Txt("Faqat mavjud", size = 13.sp)
    }
    val list = load.data
    when {
        load.error != null -> ErrorState(load.error, load.retry)
        list == null -> SkeletonList(4, 180.dp)
        list.isEmpty() -> EmptyState(Icons.Rounded.MenuBook, "Kitob topilmadi", "Qidiruv sözini özgartirib köring.")
        else -> list.chunked(2).forEachIndexed { row, pair ->
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                pair.forEachIndexed { i, b -> key(b.int("id")) { BookCard(b, Modifier.weight(1f).reveal(row * 2 + i)) } }
                if (pair.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun BookCover(title: String, url: String?, modifier: Modifier) {
    Box(modifier.clip(RoundedCornerShape(12.dp)).background(tint(title)), contentAlignment = Alignment.BottomStart) {
        Txt(title, Modifier.padding(10.dp), 13.sp, FontWeight.Bold, Color.White, 4, translate = false)
        Api.media(url)?.let { AsyncImage(it, title, Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
    }
}

@Composable
private fun BookCard(b: JSONObject, modifier: Modifier) {
    Column(modifier.press(scale = .98f) { openBook(b.int("id")) }.card().padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        BookCover(b.str("title"), b.strOrNull("cover_image_url"), Modifier.fillMaxWidth().aspectRatio(.75f))
        Txt(b.str("title"), weight = FontWeight.SemiBold, lines = 2, translate = false)
        Muted(b.str("author"), lines = 1, translate = false)
        if (b.bool("is_available")) TagGreen("${num(b.int("available_copies"))} ${t("ta mavjud")}") else TagRed("Band")
    }
}

private fun openBook(id: Int) = Sheets.show { close ->
    val scope = rememberCoroutineScope()
    val load = rememberLoad(id) { Api.get("/api/v1/library/books/$id/") }
    var msg by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    val b = load.data
    when {
        load.error != null -> ErrorState(load.error, load.retry)
        b == null -> SkeletonList(3, 80.dp)
        else -> {
            Row {
                BookCover(b.str("title"), b.strOrNull("cover_image_url"), Modifier.width(110.dp).aspectRatio(.75f))
                Spacer(Modifier.width(14.dp))
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Txt(b.str("title"), size = 19.sp, weight = FontWeight.Bold, translate = false)
                    Muted(b.str("author"), translate = false)
                    if (b.bool("is_available")) TagGreen("${num(b.int("available_copies"))} / ${num(b.int("total_copies"))} ${t("mavjud")}")
                    else TagRed("Hozir mavjud emas")
                    b.strOrNull("isbn")?.let { Tag("ISBN $it", translate = false) }
                }
            }
            Spacer(Modifier.height(12.dp))
            Txt(b.strOrNull("description") ?: "Tavsif kiritilmagan.", color = pal.text2, size = 13.5.sp, translate = b.isNull("description"))
            Spacer(Modifier.height(12.dp))
            Field(msg, { if (it.length <= 500) msg = it }, "Izoh: masalan, 2 haftaga kerak", single = false, minHeight = 66.dp)
            Spacer(Modifier.height(12.dp))
            Btn("Ijaraga ariza berish", Modifier.fillMaxWidth(), BtnKind.Primary, Icons.Rounded.Bookmark, b.bool("is_available"), busy) {
                busy = true
                scope.launch {
                    try {
                        Api.post("/api/v1/library/books/$id/request/", JSONObject().put("message", msg.trim()))
                        Toasts.show("Ariza yuborildi! Admin tasdiqlaşini kuting.")
                        close()
                    } catch (e: ApiError) { Toasts.show(e.message.orEmpty(), "err") }
                    busy = false
                }
            }
        }
    }
}

@Composable
private fun RequestsTab() {
    val scope = rememberCoroutineScope()
    var tick by remember { mutableIntStateOf(0) }
    val load = rememberLoad(tick) { Api.getAll("/api/v1/library/my/requests/") }
    val list = load.data
    when {
        load.error != null -> ErrorState(load.error, load.retry)
        list == null -> SkeletonList(4)
        list.isEmpty() -> EmptyState(Icons.Rounded.Description, "Arizalar yöq", "Kitoblar böliminda kerakli kitobni tanlab ariza qoldiring.")
        else -> GlassCard(Modifier.reveal(0).fillMaxWidth(), 14.dp) {
            list.forEach { r ->
                Row2(
                    r.str("book_title"), "${r.str("book_author")} · ${t(ago(r.str("created_at")))}", translate = false,
                    leading = { IcoBox(Icons.Rounded.MenuBook, pal.blue) },
                    trailing = {
                        Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(5.dp)) {
                            val label = r.str("status_display").ifEmpty { r.str("status") }
                            when (r.str("status")) {
                                "pending" -> TagAmber(label); "approved" -> TagGreen(label); "rejected" -> TagRed(label); "completed" -> TagBlue(label)
                                else -> Tag(label)
                            }
                            if (r.bool("can_cancel")) Btn("Bekor qiliş", kind = BtnKind.Danger, small = true) {
                                Sheets.confirm("Arizani bekor qiliş", "Haqiqatan ham bu arizani bekor qilmoqçimisiz?", "Bekor qiliş", true) {
                                    scope.launch {
                                        try { Api.post("/api/v1/library/my/requests/${r.int("id")}/cancel/"); Toasts.show("Ariza bekor qilindi") }
                                        catch (e: ApiError) { Toasts.show(e.message.orEmpty(), "err") }
                                        tick++
                                    }
                                }
                            }
                        }
                    },
                )
            }
        }
    }
}

@Composable
private fun RentalsTab() {
    val load = rememberLoad { Api.getAll("/api/v1/library/my/rentals/") }
    val list = load.data
    when {
        load.error != null -> ErrorState(load.error, load.retry)
        list == null -> SkeletonList(3, 120.dp)
        list.isEmpty() -> EmptyState(Icons.Rounded.Bookmark, "Ijaradagi kitoblar yöq")
        else -> list.forEachIndexed { i, r ->
            Row(Modifier.reveal(i).fillMaxWidth().card().padding(12.dp)) {
                BookCover(r.str("book_title"), r.strOrNull("book_cover"), Modifier.width(76.dp).aspectRatio(.75f))
                Spacer(Modifier.width(12.dp))
                Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Txt(r.str("book_title"), weight = FontWeight.SemiBold, lines = 2, translate = false)
                    Muted(r.str("book_author"), translate = false)
                    val label = r.str("status_display").ifEmpty { r.str("status") }
                    when (r.str("status")) { "active" -> TagBlue(label); "overdue" -> TagRed(label); "returned" -> TagGreen(label); else -> Tag(label) }
                    if (r.str("status") != "returned" && !r.isNull("days_until_return")) {
                        val days = r.int("days_until_return")
                        Txt(
                            if (r.bool("is_overdue")) "${num(kotlin.math.abs(days))} ${t("kun keçikdi")}" else "${num(days)} ${t("kun qoldi")}",
                            size = 12.5.sp, color = if (r.bool("is_overdue")) pal.red else pal.muted, translate = false,
                        )
                    }
                    Muted("${dateText(r.str("given_date"))} → ${dateText(r.strOrNull("actual_return_date") ?: r.str("return_date"))}", size = 11.5.sp, translate = false)
                }
            }
        }
    }
}

// ───────── Barcha bo'limlar ─────────
private class HubItem(val label: String, val sub: String, val icon: ImageVector, val c1: Long, val c2: Long, val site: String? = null, val go: (() -> Unit)? = null)

private fun hub(): List<Pair<String, List<HubItem>>> = listOf(
    "Öqiş" to listOf(
        HubItem("Kurslarim", "Darslar va davomat", Icons.Rounded.PlayCircle, 0xFFA78BFA, 0xFF7C3AED, go = { AppState.switchTab("courses") }),
        HubItem("Natijalar", "Testlar va sertifikatlar", Icons.Rounded.WorkspacePremium, 0xFFF472B6, 0xFFBE185D, go = { AppState.open(Route.Results) }),
        HubItem("Kutubxona", "Kitoblar va ijara", Icons.Rounded.MenuBook, 0xFF4ADE80, 0xFF15803D, go = { AppState.open(Route.Library) }),
        HubItem("Vazifalarim", "Uyga vazifa topşiriş", Icons.Rounded.Description, 0xFFFB923C, 0xFFC2410C, go = { AppState.open(Route.MyHomework) }),
        HubItem("Dars jadvalim", "Guruh va dars kunlari", Icons.Rounded.CalendarMonth, 0xFF2DD4BF, 0xFF0F766E, go = { AppState.open(Route.Schedule) }),
        HubItem("Video test tarixi", "Video testlar natijasi", Icons.Rounded.Videocam, 0xFFF87171, 0xFFB91C1C, "/video-quiz/history/"),
        HubItem("AI suhbat", "Savollaringizga yordam", Icons.Rounded.SmartToy, 0xFF818CF8, 0xFF4338CA, "/ai/"),
        HubItem("Sertifikat tekşiriş", "Sertifikat haqiqiyligi", Icons.Rounded.Verified, 0xFF4ADE80, 0xFF15803D, "/verify-certificate/"),
    ),
    "Coin va market" to listOf(
        HubItem("Xaridlarim", "Buyurtmalar holati", Icons.Rounded.ShoppingBag, 0xFFFB923C, 0xFFC2410C, go = { AppState.shopTab = "orders"; AppState.switchTab("shop") }),
        HubItem("Coin tarixi", "Tuşum va sarflar", Icons.Rounded.ReceiptLong, 0xFF2DD4BF, 0xFF0F766E, go = { AppState.shopTab = "history"; AppState.switchTab("shop") }),
        HubItem("Coin ötkaziş", "Dostingizga yuboring", Icons.Rounded.Send, 0xFF60A5FA, 0xFF2563EB, go = { openTransfer { } }),
        HubItem("Premium", "Tariflar va imkoniyatlar", Icons.Rounded.Star, 0xFFA78BFA, 0xFF7C3AED, go = { AppState.shopTab = "premium"; AppState.switchTab("shop") }),
    ),
    "Muloqot" to listOf(
        HubItem("Suhbatlar", "Yozişmalar", Icons.Rounded.ChatBubble, 0xFF4ADE80, 0xFF15803D, go = { AppState.open(Route.Chats) }),
        HubItem("Xabarlar", "Bildirişnomalar", Icons.Rounded.Mail, 0xFF60A5FA, 0xFF2563EB, go = { AppState.open(Route.Messages) }),
        HubItem("Postlar", "Yangiliklar va maqolalar", Icons.Rounded.Newspaper, 0xFFFB923C, 0xFFC2410C, "/blog/"),
        HubItem("Yordam", "Savol-javoblar", Icons.Rounded.HelpOutline, 0xFF2DD4BF, 0xFF0F766E, "/help/"),
    ),
    "Öyin va loyihalar" to listOf(
        HubItem("Öyinlar", "Öynang va coin toping", Icons.Rounded.SportsEsports, 0xFFF87171, 0xFFB91C1C, "/games/"),
        HubItem("Jonli öyinlar", "Boşqalar bilan bellaşing", Icons.Rounded.Bolt, 0xFFFBBF24, 0xFFB45309, "/games/live/"),
        HubItem("Startup", "Loyihangizni qurish", Icons.Rounded.RocketLaunch, 0xFF818CF8, 0xFF4338CA, "/startup/"),
    ),
    "Hisob" to listOf(
        HubItem("Profil", "Ma'lumotlar va nişonlar", Icons.Rounded.Person, 0xFFA78BFA, 0xFF7C3AED, go = { AppState.open(Route.Profile) }),
        HubItem("Sozlamalar", "Til, mavzu va ovoz", Icons.Rounded.Settings, 0xFF2DD4BF, 0xFF0F766E, go = { AppState.open(Route.SettingsPage) }),
        HubItem("Sayt sozlamalari", "Bildirişnoma va xavfsizlik", Icons.Rounded.Shield, 0xFF60A5FA, 0xFF2563EB, "/settings/"),
        HubItem("Qidiruv", "Saytdagi barça ma'lumot", Icons.Rounded.Search, 0xFFF472B6, 0xFFBE185D, "/search/"),
    ),
)

@Composable
fun MoreScreen() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val groups = remember { hub() }
    var index = 0
    Page {
        H1("Barça bölimlar", "Tashqi belgi — bölim brauzerda oçiladi", Modifier.reveal(0))
        groups.forEach { (title, items) ->
            Txt(title, size = 15.sp, weight = FontWeight.SemiBold, modifier = Modifier.reveal(index++).padding(top = 6.dp))
            items.chunked(2).forEach { pair ->
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    pair.forEach { i ->
                        var busy by remember { mutableStateOf(false) }
                        Column(
                            Modifier.weight(1f).reveal(index++).press(enabled = !busy) {
                                if (i.go != null) i.go.invoke()
                                else {
                                    busy = true
                                    scope.launch { openBrowser(ctx, Api.webUrl(i.site!!)); busy = false }
                                }
                            }.card(RoundedCornerShape(20.dp)).padding(13.dp),
                        ) {
                            Row(verticalAlignment = Alignment.Top) {
                                Box(
                                    Modifier.size(46.dp).clip(RoundedCornerShape(13.dp)).background(Brush.linearGradient(listOf(Color(i.c1), Color(i.c2)))),
                                    contentAlignment = Alignment.Center,
                                ) { if (busy) Spinner(20.dp, Color.White) else Icon(i.icon, null, Modifier.size(23.dp), Color.White) }
                                Spacer(Modifier.weight(1f))
                                if (i.site != null) Icon(Icons.Rounded.OpenInNew, t("Brauzerda oçiladi"), Modifier.size(15.dp), pal.muted)
                            }
                            Spacer(Modifier.height(10.dp))
                            Txt(i.label, weight = FontWeight.SemiBold, lines = 1)
                            Muted(i.sub, size = 12.sp, lines = 1)
                        }
                    }
                    if (pair.size == 1) Spacer(Modifier.weight(1f))
                }
            }
        }
    }
}
