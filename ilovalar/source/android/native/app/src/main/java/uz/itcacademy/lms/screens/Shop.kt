package uz.itcacademy.lms.screens

import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.background
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import uz.itcacademy.lms.*
import uz.itcacademy.lms.ui.*

private val SHOP_TABS = listOf("products" to "Mahsulotlar", "orders" to "Xaridlarim", "history" to "Tarix", "premium" to "Premium")

@Composable
fun ShopScreen() {
    val scope = rememberCoroutineScope()
    var version by remember { mutableIntStateOf(0) }
    val summary = rememberLoad(version) { Api.get("/api/v1/coin/summary/") }
    val tab = AppState.shopTab
    val changed: () -> Unit = { version++; scope.launch { AppState.refreshUser() } }

    Page {
        Row(Modifier.reveal(0), verticalAlignment = Alignment.CenterVertically) {
            H1("Coin dökon", null, Modifier.weight(1f))
            Btn("Ötkaziş", small = true, icon = Icons.Rounded.Send) { openTransfer(changed) }
        }
        summary.data?.let { s ->
            Row(Modifier.reveal(1), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Column(Modifier.weight(1f).card(RoundedCornerShape(18.dp)).padding(12.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) { CoinDot(18.dp); Spacer(Modifier.width(5.dp)); CountUp(s.int("total_coins"), 19.sp) }
                    Muted("Joriy balans", size = 11.5.sp)
                }
                Column(Modifier.weight(1f).card(RoundedCornerShape(18.dp)).padding(12.dp)) { CountUp(s.int("total_earned"), 19.sp, pal.green); Muted("Jami topilgan", size = 11.5.sp, lines = 1) }
                Column(Modifier.weight(1f).card(RoundedCornerShape(18.dp)).padding(12.dp)) { CountUp(s.int("total_spent"), 19.sp); Muted("Jami sarflangan", size = 11.5.sp, lines = 1) }
            }
        }
        Chips(SHOP_TABS, tab, Modifier.reveal(2)) { AppState.shopTab = it }
        when (tab) {
            "orders" -> OrdersTab(version, changed)
            "history" -> HistoryTab()
            "premium" -> PremiumTab(version, changed)
            else -> ProductsTab(version, changed)
        }
    }
}

@Composable
private fun ProductsTab(version: Int, changed: () -> Unit) {
    var q by remember { mutableStateOf("") }
    val load = rememberLoad(version) { Api.getAll("/api/v1/coin/products/") }
    val list = load.data
    Field(q, { q = it }, "Mahsulot qidiriş", icon = Icons.Rounded.Search)
    when {
        load.error != null -> ErrorState(load.error, load.retry)
        list == null -> SkeletonList(3, 240.dp)
        else -> {
            val shown = list.filter { it.str("name").contains(q.trim(), true) }
            if (shown.isEmpty()) EmptyState(Icons.Rounded.CardGiftcard, if (list.isEmpty()) "Hozirça mahsulotlar yöq" else "Hech narsa topilmadi")
            shown.chunked(2).forEachIndexed { row, pair ->
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    pair.forEachIndexed { i, p -> key(p.int("id")) { ProductCard(p, Modifier.weight(1f).reveal(row * 2 + i), changed) } }
                    if (pair.size == 1) Spacer(Modifier.weight(1f))
                }
            }
        }
    }
}

private fun priceOf(p: JSONObject) = if (p.isNull("discounted_price")) p.int("coin_price") else p.int("discounted_price")

@Composable
private fun ProductCard(p: JSONObject, modifier: Modifier, changed: () -> Unit) {
    val scope = rememberCoroutineScope()
    var liked by remember { mutableStateOf(p.bool("is_liked")) }
    var likes by remember { mutableIntStateOf(p.int("likes_count")) }
    val out = p.int("stock") <= 0
    val heart by animateFloatAsState(if (liked) 1.15f else 1f, spring(.35f, Spring.StiffnessMedium), label = "h")
    Column(modifier.press(scale = .98f) { openProduct(p, changed) }.card()) {
        Box(Modifier.fillMaxWidth().aspectRatio(1.1f).background(pal.a1.copy(alpha = .2f)), contentAlignment = Alignment.Center) {
            Icon(Icons.Rounded.CardGiftcard, null, Modifier.size(38.dp), pal.text2)
            Api.media(p.strOrNull("image"))?.let { AsyncImage(it, p.str("name"), Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
            if (p.bool("has_discount")) Box(Modifier.align(Alignment.TopStart).padding(8.dp)) { Tag("−${p.int("discount_percent")}%", Color.White, Color(0xB3101020), translate = false) }
            Tinted(Color(0x8C0A0A14), Modifier.align(Alignment.TopEnd).padding(8.dp).size(32.dp).press {
                scope.launch {
                    try {
                        val r = Api.post("/api/v1/coin/products/${p.int("id")}/like/")
                        liked = r.bool("liked"); likes = r.int("likes_count")
                    } catch (e: ApiError) { Toasts.show(e.message.orEmpty(), "err") }
                }
            }, CircleShape) {
                Icon(
                    if (liked) Icons.Rounded.Favorite else Icons.Rounded.FavoriteBorder, t("Yoqdi"),
                    Modifier.size(17.dp).graphicsLayer { scaleX = heart; scaleY = heart }, if (liked) Color(0xFFF43F5E) else Color.White,
                )
            }
        }
        Column(Modifier.padding(11.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Txt(p.str("name"), weight = FontWeight.SemiBold, lines = 2, translate = false)
            Muted(if (out) "Tugagan" else "${num(p.int("stock"))} ${t("ta qoldi")}", size = 11.5.sp, translate = false)
            Row(verticalAlignment = Alignment.CenterVertically) {
                CoinDot(16.dp); Spacer(Modifier.width(4.dp))
                Txt(num(priceOf(p)), Modifier.weight(1f), 15.sp, FontWeight.Bold, translate = false, lines = 1)
                if (p.bool("premium_only")) Icon(Icons.Rounded.WorkspacePremium, null, Modifier.size(16.dp), Color(0xFFF97316))
            }
        }
    }
}

private fun confirmBuy(p: JSONObject, onOk: () -> Unit) {
    val price = priceOf(p)
    val coins = AppState.user?.int("coins") ?: 0
    if (coins < price) {
        Toasts.show("${t("Coinlaringiz yetarli emas")}. ${num(price)} / ${num(coins)}", "err")
        return
    }
    Sheets.confirm(
        "Xaridni tasdiqlang",
        "${p.str("name")}: ${num(price)} coin. ${t("Xariddan keyin balansingiz")}: ${num(coins - price)} coin.",
        "Sotib oliş",
    ) {
        LessonScope.launch {
            try {
                Api.post("/api/v1/coin/products/${p.int("id")}/purchase/")
                Toasts.show("\"${p.str("name")}\" ${t("buyurtma qilindi!")}")
                AppState.refreshUser()
                onOk()
            } catch (e: ApiError) { Toasts.show(e.message.orEmpty(), "err") }
        }
    }
}

object LessonScope {
    private val s = kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.Main + kotlinx.coroutines.SupervisorJob())
    fun launch(block: suspend () -> Unit) = s.launch { block() }
}

private fun openProduct(p: JSONObject, changed: () -> Unit) = Sheets.show { close ->
    val scope = rememberCoroutineScope()
    val out = p.int("stock") <= 0
    var text by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var reload by remember { mutableIntStateOf(0) }
    val comments = rememberLoad(reload) { Api.getAll("/api/v1/coin/products/${p.int("id")}/comments/", max = 3) }

    Api.media(p.strOrNull("image"))?.let {
        AsyncImage(it, null, Modifier.fillMaxWidth().height(200.dp).clip(RoundedCornerShape(18.dp)), contentScale = ContentScale.Crop)
        Spacer(Modifier.height(12.dp))
    }
    Txt(p.str("name"), size = 21.sp, weight = FontWeight.Bold, translate = false)
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 6.dp)) {
        CoinDot(24.dp); Spacer(Modifier.width(6.dp))
        Txt(num(priceOf(p)), size = 24.sp, weight = FontWeight.Bold, translate = false)
        if (p.bool("has_discount")) {
            Spacer(Modifier.width(8.dp))
            androidx.compose.material3.Text(num(p.int("coin_price")), color = pal.muted, textDecoration = TextDecoration.LineThrough, fontSize = 13.sp)
        }
    }
    stripHtml(p.strOrNull("description")).takeIf { it.isNotEmpty() }?.let { Txt(it, color = pal.text2, size = 13.5.sp, translate = false) }
    Spacer(Modifier.height(12.dp))
    Btn(if (out) "Tugagan" else "Sotib oliş", Modifier.fillMaxWidth(), BtnKind.Primary, Icons.Rounded.ShoppingBag, !out) {
        confirmBuy(p) { close(); changed() }
    }
    Spacer(Modifier.height(16.dp))
    Txt("Izohlar", size = 15.sp, weight = FontWeight.SemiBold)
    val list = comments.data
    if (list == null) SkeletonList(2, 48.dp)
    else if (list.isEmpty()) Muted("Hali izoh yöq — birinçi bölib yozing.", Modifier.padding(vertical = 8.dp))
    else list.take(10).forEach { c ->
        Row2(
            c.str("full_name").ifEmpty { c.str("username") }, c.str("content"), translate = false,
            leading = { Avatar(null, c.str("full_name").ifEmpty { c.str("username") }, 30.dp) },
        )
    }
    Spacer(Modifier.height(8.dp))
    Field(text, { if (it.length <= 500) text = it }, "Fikringizni yozing…", single = false, minHeight = 70.dp)
    Muted(
        if (AppState.user?.bool("is_premium") == true) "Premium: izoh uçun +1 coin olasiz" else "Izoh yoziş 1 coin turadi · soatiga 1 ta",
        Modifier.padding(vertical = 6.dp), 12.sp,
    )
    Btn("Yuboriş", small = true, icon = Icons.Rounded.Send, busy = sending, enabled = text.isNotBlank()) {
        sending = true
        scope.launch {
            try {
                Api.post("/api/v1/coin/products/${p.int("id")}/comments/add/", JSONObject().put("content", text.trim()))
                text = ""
                Toasts.show("Izoh qoldirildi")
                reload++
                AppState.refreshUser()
            } catch (e: ApiError) { Toasts.show(e.message.orEmpty(), "err") }
            sending = false
        }
    }
}

@Composable
private fun OrdersTab(version: Int, changed: () -> Unit) {
    val scope = rememberCoroutineScope()
    var tick by remember { mutableIntStateOf(0) }
    val load = rememberLoad(version, tick) { Api.getAll("/api/v1/coin/my-purchases/") }
    val list = load.data
    when {
        load.error != null -> ErrorState(load.error, load.retry)
        list == null -> SkeletonList(5)
        list.isEmpty() -> EmptyState(Icons.Rounded.ShoppingBag, "Hali xarid qilmagansiz", "Mahsulotlar böliminda coinlaringizga sovğa tanlang.") {
            Btn("Mahsulotlar", kind = BtnKind.Primary, icon = Icons.Rounded.CardGiftcard) { AppState.shopTab = "products" }
        }
        else -> GlassCard(Modifier.reveal(3).fillMaxWidth(), 14.dp) {
            list.forEach { o ->
                Row2(
                    o.str("product_name"), "${t("Buyurtma")} #${o.int("id")} · ${t(ago(o.str("purchased_at")))} · ${num(o.int("coins_spent"))} coin",
                    translate = false,
                    leading = { IcoBox(Icons.Rounded.CardGiftcard, pal.a1) },
                    trailing = {
                        Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(5.dp)) {
                            when (o.str("status")) {
                                "pending" -> TagAmber("Kutilmoqda")
                                "delivered" -> TagGreen("Yetkazildi")
                                "completed" -> TagGreen("Bajarildi")
                                "cancelled" -> TagRed("Bekor qilindi")
                                else -> if (o.bool("is_delivered")) TagGreen("Yetkazildi") else Tag(o.str("status"))
                            }
                            if (o.bool("can_cancel")) Btn("Bekor qiliş", kind = BtnKind.Danger, small = true) {
                                Sheets.confirm("Buyurtmani bekor qiliş", "Coinlar balansingizga qaytariladi. Davom etasizmi?", "Bekor qiliş", true) {
                                    scope.launch {
                                        try {
                                            Api.post("/api/v1/coin/purchases/${o.int("id")}/cancel/")
                                            Toasts.show("Buyurtma bekor qilindi, coinlar qaytarildi")
                                            changed()
                                        } catch (e: ApiError) { Toasts.show(e.message.orEmpty(), "err") }
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
private fun HistoryTab() {
    val load = rememberLoad { Api.getAll("/api/v1/coin/transactions/", max = 5) }
    val list = load.data
    when {
        load.error != null -> ErrorState(load.error, load.retry)
        list == null -> SkeletonList(6)
        list.isEmpty() -> EmptyState(Icons.Rounded.ReceiptLong, "Tranzaksiyalar yöq")
        else -> GlassCard(Modifier.reveal(3).fillMaxWidth(), 14.dp) { list.forEach { TxRow(it) } }
    }
}

@Composable
private fun PremiumTab(version: Int, changed: () -> Unit) {
    var tick by remember { mutableIntStateOf(0) }
    val load = rememberLoad(version, tick) { Api.get("/api/v1/coin/premium/plans/") }
    val d = load.data
    when {
        load.error != null -> ErrorState(load.error, load.retry)
        d == null -> SkeletonList(3, 160.dp)
        else -> {
            if (d.bool("is_premium")) Notice(Icons.Rounded.WorkspacePremium, "Siz Premium a'zosiz!", d.strOrNull("premium_expires_at")?.let { "${t("Amal qiladi")}: ${dateText(it)}" })
            if (d.bool("has_pending_request")) Notice(Icons.Rounded.Schedule, "Sörovingiz körib çiqilmoqda.", "Admin tasdiqlaşini kuting.")
            if (!d.bool("eligible")) Notice(Icons.Rounded.Info, "Premium sotib oliş uçun röyxatdan ötganingizga kamida 1 oy bölişi kerak.", "${num(d.int("days_until_eligible"))} ${t("kun qoldi")}")
            val plans = d.optJSONObject("plans") ?: JSONObject()
            var i = 0
            plans.keys().forEach { key ->
                val p = plans.getJSONObject(key)
                val index = i++
                val disabled = !d.bool("eligible") || d.bool("has_pending_request") || p.bool("too_cheap")
                GlassCard(Modifier.reveal(index + 3).fillMaxWidth(), fill = if (index == 1) pal.a1.copy(alpha = .14f) else null) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IcoBox(Icons.Rounded.WorkspacePremium, pal.amber)
                        Spacer(Modifier.width(10.dp))
                        Txt(p.str("name").ifEmpty { key }, Modifier.weight(1f), 17.sp, FontWeight.Bold)
                        if (index == 1) TagAccent("Ommabop")
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 8.dp)) {
                        CoinDot(26.dp); Spacer(Modifier.width(7.dp))
                        Txt(num(p.int("price")), size = 27.sp, weight = FontWeight.ExtraBold, translate = false)
                    }
                    if (p.bool("too_cheap")) Txt("${t("Kamida")} ${num(p.int("min_price"))} ${t("coin yiğiş kerak")}", color = pal.amber, size = 12.5.sp, translate = false)
                    else Muted("${num(p.int("days"))} ${t("kun")} · ${num(p.int("percent"))}%", translate = false)
                    Spacer(Modifier.height(10.dp))
                    Btn(if (d.bool("is_premium")) "Uzaytiriş" else "Sotib oliş", Modifier.fillMaxWidth(), if (index == 1) BtnKind.Primary else BtnKind.Normal, enabled = !disabled) {
                        Sheets.confirm("Premium sörov", "${p.str("name")}: ${num(p.int("price"))} coin ${t("yeçiladi va sörov adminga yuboriladi.")}", "Yuboriş") {
                            LessonScope.launch {
                                try {
                                    val r = Api.post("/api/v1/coin/premium/request/", JSONObject().put("plan", key))
                                    Toasts.show(r.strOrNull("message") ?: "Sörov yuborildi")
                                    changed()
                                } catch (e: ApiError) { Toasts.show(e.message.orEmpty(), "err") }
                                tick++
                            }
                        }
                    }
                }
            }
            GlassCard(Modifier.fillMaxWidth()) {
                SectionTitle("Premium afzalliklari", Icons.Rounded.AutoAwesome)
                listOf("Dökonda 5% çegirma", "Profil bezaklari va maxsus nişon", "Yangi mahsulotlarga erta kiriş", "Izoh yozganda coin olasiz").forEach {
                    Row(Modifier.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Rounded.Check, null, Modifier.size(17.dp), pal.green); Spacer(Modifier.width(8.dp)); Txt(it, size = 13.5.sp)
                    }
                }
            }
        }
    }
}

@Composable
fun Notice(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, sub: String? = null) {
    Row(Modifier.fillMaxWidth().card(fill = pal.a1.copy(alpha = .12f)).padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, null, Modifier.size(22.dp), pal.a1); Spacer(Modifier.width(10.dp))
        Column { Txt(title, weight = FontWeight.SemiBold); if (sub != null) Muted(sub) }
    }
}

/** Coin o'tkazish: qabul qiluvchi, miqdor, tasdiqlash (Telegram kodi yoki parol). */
fun openTransfer(onDone: () -> Unit) = Sheets.show { close ->
    val scope = rememberCoroutineScope()
    var step by remember { mutableIntStateOf(1) }
    var to by remember { mutableStateOf<JSONObject?>(null) }
    var amount by remember { mutableStateOf("500") }
    var transfer by remember { mutableStateOf<JSONObject?>(null) }
    var busy by remember { mutableStateOf(false) }
    var success by remember { mutableStateOf<JSONObject?>(null) }

    Txt("Coin ötkaziş", size = 19.sp, weight = FontWeight.Bold)
    Spacer(Modifier.height(10.dp))
    if (success != null) {
        val s = success!!
        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
            val g = growIn(durationMs = 500)
            Tinted(pal.green.copy(alpha = .15f), Modifier.size(72.dp).graphicsLayer { scaleX = g; scaleY = g }, CircleShape) { Icon(Icons.Rounded.Check, null, Modifier.size(34.dp), pal.green) }
            Txt("Ötkazma bajarildi!", size = 21.sp, weight = FontWeight.Bold, modifier = Modifier.padding(top = 12.dp))
            s.strOrNull("message")?.let { Muted(it, Modifier.padding(top = 4.dp)) }
            Muted("${t("Yangi balans")}: ${num(s.int("new_balance"))} coin", Modifier.padding(vertical = 8.dp), translate = false)
            Btn("Tayyor", kind = BtnKind.Primary, onClick = close)
        }
        return@show
    }
    Row(Modifier.fillMaxWidth().padding(bottom = 14.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        listOf("Qabul qiluvçi", "Miqdor", "Tasdiqlaş").forEachIndexed { i, s ->
            Column(Modifier.weight(1f)) {
                ProgressBar(if (step > i) 1f else 0f, height = 4.dp)
                Muted(s, Modifier.padding(top = 4.dp), 11.sp, 1)
            }
        }
    }
    when (step) {
        1 -> {
            var q by remember { mutableStateOf("") }
            var query by remember { mutableStateOf("") }
            LaunchedEffect(q) { delay(300); query = q.trim() }
            Field(q, { q = it }, "Login, ism yoki telefon raqam", icon = Icons.Rounded.Search)
            if (query.length < 2) Muted("Kamida 2 ta belgi kiriting.", Modifier.padding(vertical = 18.dp))
            else {
                val load = rememberLoad(query) { Api.rows(Api.getAny("/api/v1/coin/transfer/search/", mapOf("username" to query))) }
                val found = load.data
                when {
                    load.error != null -> Muted(load.error.message.orEmpty(), Modifier.padding(vertical = 18.dp), translate = false)
                    found == null -> Box(Modifier.padding(top = 10.dp)) { SkeletonList(2, 50.dp) }
                    found.isEmpty() -> Muted("Foydalanuvçi topilmadi.", Modifier.padding(vertical = 18.dp))
                    else -> found.forEach { u ->
                        Row2(
                            u.str("full_name").ifEmpty { u.str("username") }, "@${u.str("username")}", translate = false,
                            leading = { Avatar(u.strOrNull("photo"), u.str("full_name").ifEmpty { u.str("username") }, 38.dp) },
                            trailing = { Icon(Icons.Rounded.ChevronRight, null, Modifier.size(20.dp), pal.muted) },
                        ) { to = u; step = 2 }
                    }
                }
            }
        }
        2 -> {
            val u = to!!
            val a = amount.toIntOrNull() ?: 0
            val fee = (a + 9) / 10
            val total = a + fee
            val bal = AppState.user?.int("coins") ?: 0
            val okRange = a in 100..10000
            val okBal = total <= bal
            Row2(u.str("full_name").ifEmpty { u.str("username") }, "@${u.str("username")}", translate = false, leading = { Avatar(u.strOrNull("photo"), u.str("username"), 38.dp) })
            Field(amount, { amount = it.filter(Char::isDigit).take(5) }, "Miqdor (100 – 10 000 coin)", keyboard = KeyboardType.Number)
            Row(Modifier.padding(vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(100, 500, 1000, 2000).forEach { v -> Btn(num(v), small = true) { amount = v.toString() } }
            }
            KV("Ötkaziladi", "${num(a)} coin"); KV("Xizmat haqqi (10%)", "${num(fee)} coin"); KV("Jami yeçiladi", "${num(total)} coin", true)
            KV("Balansingiz qoladi", "${num(bal - total)} coin")
            if (!okRange) Txt("Miqdor 100 dan 10 000 gaça bölişi kerak.", color = pal.red, size = 12.5.sp)
            else if (!okBal) Txt("Coinlaringiz yetarli emas.", color = pal.red, size = 12.5.sp)
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Btn("Orqaga", Modifier.weight(1f)) { step = 1 }
                Btn("Davom etiş", Modifier.weight(1f), BtnKind.Primary, busy = busy, enabled = okRange && okBal) {
                    busy = true
                    scope.launch {
                        try {
                            transfer = Api.post("/api/v1/coin/transfer/initiate/", JSONObject().put("receiver_username", u.str("username")).put("amount", a))
                            step = 3
                        } catch (e: ApiError) { Toasts.show(e.message.orEmpty(), "err") }
                        busy = false
                    }
                }
            }
        }
        else -> {
            val tr = transfer!!
            val tg = tr.bool("needs_telegram_code")
            var code by remember { mutableStateOf("") }
            var left by remember { mutableIntStateOf(120) }
            LaunchedEffect(Unit) { while (left > 0) { delay(1000); left-- } }
            Column(Modifier.fillMaxWidth().card(fill = pal.a1.copy(alpha = .13f)).padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Muted("Siz ötkazmoqdasiz")
                Row(verticalAlignment = Alignment.CenterVertically) { CoinDot(28.dp); Spacer(Modifier.width(8.dp)); Txt(num(tr.int("amount")), size = 34.sp, weight = FontWeight.ExtraBold, translate = false) }
                Muted("${tr.str("receiver")} (@${tr.str("receiver_username")}) · ${t("jami")} ${num(tr.int("total_deducted"))} coin", translate = false)
            }
            Spacer(Modifier.height(12.dp))
            Field(
                code, { code = if (tg) it.filter(Char::isDigit).take(6) else it },
                if (tg) "Telegramga yuborilgan 6 xonali kod" else "Tasdiqlaş uçun parolingiz",
                password = !tg, keyboard = if (tg) KeyboardType.Number else KeyboardType.Text,
            )
            if (left > 0) Muted("${t("Kod amal qiladi")}: %d:%02d".format(left / 60, left % 60), Modifier.padding(vertical = 8.dp), translate = false)
            else Txt("Muddat tugadi — qaytadan boşlang.", Modifier.padding(vertical = 8.dp), color = pal.red, size = 12.5.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Btn("Bekor qiliş", Modifier.weight(1f), onClick = close)
                Btn("Tasdiqlaş", Modifier.weight(1f), BtnKind.Primary, Icons.Rounded.Shield, left > 0 && code.isNotBlank(), busy) {
                    busy = true
                    scope.launch {
                        try {
                            val body = JSONObject().put("transfer_id", tr.get("id"))
                            if (tg) body.put("code", code.trim()) else body.put("password", code)
                            success = Api.post("/api/v1/coin/transfer/confirm/", body)
                            AppState.refreshUser()
                            onDone()
                        } catch (e: ApiError) { Toasts.show(e.message.orEmpty(), "err") }
                        busy = false
                    }
                }
            }
        }
    }
}

@Composable
private fun KV(k: String, v: String, bold: Boolean = false) {
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
        Txt(k, Modifier.weight(1f), 13.sp, color = pal.text2)
        Txt(v, size = 13.sp, weight = if (bold) FontWeight.Bold else FontWeight.SemiBold, translate = false)
    }
}
