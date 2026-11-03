package uz.itcacademy.lms.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONObject
import uz.itcacademy.lms.*
import uz.itcacademy.lms.ui.*
import java.util.Calendar

val LESSON_TYPE = mapOf("video" to "Video dars", "homework" to "Uyga vazifa", "test" to "Test", "dictionary" to "Luğat", "speaking" to "Speaking")

fun lessonIcon(type: String): ImageVector = when (type) {
    "video" -> Icons.Rounded.PlayCircle
    "homework" -> Icons.Rounded.Description
    "test" -> Icons.Rounded.TaskAlt
    "dictionary" -> Icons.Rounded.Translate
    "speaking" -> Icons.Rounded.Mic
    else -> Icons.Rounded.Article
}

@Composable
fun lessonColor(type: String): Color = when (type) {
    "video" -> pal.red
    "homework" -> pal.blue
    "test" -> pal.green
    "dictionary" -> pal.amber
    "speaking" -> Color(0xFFEC4899)
    else -> pal.a1
}

private class HomeData(
    val enrollments: List<JSONObject>?, val enrollCount: Int, val results: List<JSONObject>?, val certs: Int?,
    val txs: List<JSONObject>?, val top: JSONObject?,
)

private suspend fun <T> attempt(block: suspend () -> T): T? = try { block() } catch (_: ApiError) { null }

@Composable
fun HomeScreen() {
    val u = AppState.user ?: return
    val recent = remember { Settings.recent() }
    val ctx = LocalContext.current
    val load = rememberLoad {
        val enr = attempt { Api.getAny("/api/v1/my/enrollments/") }
        val res = attempt { Api.rows(Api.getAny("/api/v1/my/test-results/")) }
        val cert = attempt { Api.getAny("/api/v1/my/certificates/") }
        HomeData(
            enr?.let { Api.rows(it) }, (enr as? JSONObject)?.optInt("count", Api.rows(enr).size) ?: Api.rows(enr).size,
            res, cert?.let { (it as? JSONObject)?.optInt("count", Api.rows(it).size) ?: Api.rows(it).size },
            attempt { Api.getAll("/api/v1/coin/transactions/", max = 4) },
            attempt { Api.get("/api/v1/reyting/", mapOf("tab" to "coins", "limit" to 5)) },
        )
    }
    val d = load.data
    val name = u.str("first_name").ifEmpty { u.str("full_name").ifEmpty { u.str("username") } }

    Page {
        Row(Modifier.fillMaxWidth().reveal(0), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Muted(dateText(java.time.LocalDate.now().toString()))
                Txt("${t(greeting())}, $name!", size = 25.sp, weight = FontWeight.Bold, spacing = (-.5).sp, lines = 2, translate = false)
            }
            Box(Modifier.press { AppState.open(Route.Profile) }) { Avatar(u.strOrNull("photo"), u.str("full_name").ifEmpty { u.str("username") }, 46.dp) }
        }

        // Asosiy karta
        Column(
            Modifier.reveal(1).fillMaxWidth().clip(RoundedCornerShape(26.dp))
                .background(Brush.linearGradient(listOf(pal.a1, pal.a2, pal.a3))).padding(20.dp),
        ) {
            Text2(if (recent.isNotEmpty()) "${t("Oxirgi marta")}: ${recent[0].str("title")}" else "Bugun ham yangi narsa örganiş uçun ajoyib kun.")
            Spacer(Modifier.height(14.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                HeroPill("Coin balans", Modifier.weight(1f)) { Row(verticalAlignment = Alignment.CenterVertically) { CoinDot(20.dp); Spacer(Modifier.width(6.dp)); CountUp(u.int("coins"), 22.sp, Color.White) } }
                HeroPill("Reytingdagi örin", Modifier.weight(1f)) {
                    val rank = d?.top?.int("user_rank") ?: 0
                    Txt(if (rank > 0) "#${num(rank)}" else "—", size = 22.sp, weight = FontWeight.Bold, color = Color.White, translate = false)
                }
            }
            Spacer(Modifier.height(14.dp))
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(
                    Modifier.press {
                        val r = recent.firstOrNull()
                        if (r != null) openLessonById(r) else AppState.switchTab("courses")
                    }.clip(RoundedCornerShape(13.dp)).background(Color.White).padding(horizontal = 14.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Rounded.PlayArrow, null, Modifier.size(18.dp), Color(0xFF1A1033)); Spacer(Modifier.width(6.dp))
                    Txt(if (recent.isNotEmpty()) "Davom ettiriş" else "Darslarni boşlaş", size = 13.5.sp, weight = FontWeight.SemiBold, color = Color(0xFF1A1033))
                }
                if (u.bool("is_premium")) TagPremium()
            }
        }

        // Statistika
        Row(Modifier.reveal(2), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            StatTile(Icons.Rounded.PlayCircle, pal.a1, "Kurslarim", d?.enrollCount, Modifier.weight(1f)) { AppState.switchTab("courses") }
            StatTile(Icons.Rounded.CheckCircle, pal.green, "Testlar", d?.results?.count { it.bool("passed") }, Modifier.weight(1f)) { AppState.open(Route.Results) }
            StatTile(Icons.Rounded.WorkspacePremium, pal.amber, "Sertifikatlar", d?.certs, Modifier.weight(1f)) { AppState.open(Route.Results) }
        }

        if (!u.bool("is_profile_completed")) {
            Row(Modifier.reveal(3).fillMaxWidth().card(fill = pal.amber.copy(alpha = .13f)).padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.WarningAmber, null, Modifier.size(22.dp), pal.amber); Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Txt("Profilingiz töliq emas", weight = FontWeight.SemiBold)
                    Muted("Kurslar va natijalar körinişi uçun ma'lumotlaringizni töldiring.")
                }
                Spacer(Modifier.width(8.dp))
                OpenSiteButton("Töldiriş", "/profile/complete/")
            }
        }

        if (recent.isNotEmpty()) {
            Column(Modifier.reveal(3)) {
                SectionTitle("Davom ettiriş", Icons.Rounded.History)
                recent.take(3).forEach { r ->
                    Row2(
                        r.str("title"), r.str("course"), translate = false,
                        leading = { IcoBox(lessonIcon(r.str("type")), lessonColor(r.str("type"))) },
                        trailing = { Icon(Icons.Rounded.PlayCircle, null, Modifier.size(26.dp), pal.a1) },
                    ) { openLessonById(r) }
                }
            }
        }

        if (d == null && load.loading) SkeletonList(3, 120.dp)

        d?.txs?.let { CoinActivity(it, Modifier.reveal(4)) }

        d?.enrollments?.let { list ->
            GlassCard(Modifier.reveal(5).fillMaxWidth()) {
                SectionTitle("Mening kurslarim", Icons.Rounded.PlayCircle, "Barçasi") { AppState.switchTab("courses") }
                if (list.isEmpty()) EmptyState(Icons.Rounded.PlayCircle, "Hali kursga yozilmagansiz", "Barça kurslar röyxatidan özingizga mosini tanlang.")
                list.take(3).forEach { e ->
                    val p = e.optJSONObject("profession") ?: return@forEach
                    Row2(
                        p.str("name"), "${num(p.int("student_count"))} ${t("öquvçi")}", translate = false,
                        leading = { CourseThumb(p, 44.dp) },
                        trailing = { Icon(Icons.Rounded.ChevronRight, null, Modifier.size(20.dp), pal.muted) },
                    ) { AppState.open(Route.Course(p.int("id"))) }
                }
            }
        }

        d?.results?.let { list ->
            GlassCard(Modifier.reveal(6).fillMaxWidth()) {
                SectionTitle("Oxirgi natijalar", Icons.Rounded.TaskAlt, "Barçasi") { AppState.open(Route.Results) }
                if (list.isEmpty()) EmptyState(Icons.Rounded.TaskAlt, "Hali test topşirilmagan")
                list.take(4).forEach { ResultRow(it) }
            }
        }

        d?.top?.let { top ->
            GlassCard(Modifier.reveal(7).fillMaxWidth()) {
                SectionTitle("Reyting — top 5", Icons.Rounded.EmojiEvents, "Töliq") { AppState.switchTab("rating") }
                Api.rowsOf(top, "students").forEach { s -> RankRow(s, true) }
            }
        }

        d?.txs?.let { list ->
            GlassCard(Modifier.reveal(8).fillMaxWidth()) {
                SectionTitle("Coin tarixi", Icons.Rounded.ReceiptLong, "Barçasi") { AppState.shopTab = "history"; AppState.switchTab("shop") }
                if (list.isEmpty()) EmptyState(Icons.Rounded.ReceiptLong, "Hali tranzaksiyalar yöq")
                list.take(5).forEach { TxRow(it) }
            }
        }
    }
}

@Composable private fun Text2(s: String) = Txt(s, color = Color.White.copy(alpha = .92f), size = 14.sp, lines = 2)

@Composable
private fun HeroPill(label: String, modifier: Modifier, content: @Composable () -> Unit) {
    Column(modifier.clip(RoundedCornerShape(16.dp)).background(Color.White.copy(alpha = .17f)).padding(12.dp)) {
        Txt(label, size = 11.5.sp, color = Color.White.copy(alpha = .86f), lines = 1)
        Spacer(Modifier.height(4.dp))
        content()
    }
}

@Composable
private fun StatTile(icon: ImageVector, color: Color, label: String, value: Int?, modifier: Modifier, onClick: () -> Unit) {
    Column(modifier.press(onClick = onClick).card(RoundedCornerShape(18.dp)).padding(13.dp)) {
        IcoBox(icon, color, 34.dp)
        Spacer(Modifier.height(9.dp))
        if (value != null) CountUp(value, 22.sp) else Txt("—", size = 22.sp, weight = FontWeight.Bold)
        Muted(label, size = 11.5.sp, lines = 1)
    }
}

/** Oxirgi 14 kunlik coin faolligi. */
@Composable
fun CoinActivity(txs: List<JSONObject>, modifier: Modifier = Modifier) {
    var kind by remember { mutableIntStateOf(0) }
    val days = remember(txs) {
        val start = Calendar.getInstance().apply { set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0) }
        val arr = Array(14) { i -> (start.clone() as Calendar).apply { add(Calendar.DAY_OF_YEAR, i - 13) } }
        val earned = IntArray(14)
        val spent = IntArray(14)
        val base = arr[0].timeInMillis
        txs.forEach { tx ->
            val d = parseDate(tx.str("created_at")) ?: return@forEach
            val i = ((d.time - base) / 86_400_000L).toInt()
            if (i !in 0..13) return@forEach
            if (tx.str("action") == "add") earned[i] += tx.int("amount") else spent[i] += tx.int("amount")
        }
        Triple(arr, earned, spent)
    }
    val values = if (kind == 0) days.second else days.third
    val total = values.sum()
    val now = values.drop(7).sum()
    val last = values.take(7).sum()
    GlassCard(modifier.fillMaxWidth()) {
        SectionTitle("Coin faolligi", Icons.Rounded.BarChart)
        Segmented(listOf("Topilgan", "Sarflangan"), kind) { kind = it }
        Spacer(Modifier.height(12.dp))
        Row(verticalAlignment = Alignment.Bottom) {
            Txt(num(total), size = 25.sp, weight = FontWeight.Bold, translate = false)
            Spacer(Modifier.width(6.dp))
            Muted(if (kind == 0) "coin topildi" else "coin sarflandi", Modifier.padding(bottom = 4.dp))
            if (last > 0) {
                val pct = (now - last) * 100 / last
                Spacer(Modifier.width(8.dp))
                Txt(
                    "${if (pct >= 0) "+" else ""}$pct%", Modifier.padding(bottom = 4.dp), 12.5.sp, FontWeight.SemiBold, translate = false,
                    color = if (kind != 0) pal.text2 else if (pct >= 0) pal.green else pal.red,
                )
            }
        }
        if (total == 0) {
            EmptyState(Icons.Rounded.BarChart, if (kind == 0) "Bu davrda coin topilmagan" else "Bu davrda coin sarflanmagan")
        } else {
            key(kind) {
                ColumnChart(
                    (0 until 14).map { i -> ChartPoint("${days.first[i].get(Calendar.DAY_OF_MONTH)}", values[i]) },
                    Modifier.padding(top = 4.dp),
                )
            }
        }
    }
}

@Composable
fun ResultRow(r: JSONObject) {
    val total = r.int("total_questions")
    val pct = if (total > 0) r.int("correct_answers") * 100 / total else r.int("score").coerceAtMost(100)
    val passed = r.bool("passed")
    Row2(
        r.str("test_name").ifEmpty { "Test" },
        "${num(r.int("correct_answers"))} / ${num(total)} ${t("töğri")} · ${num(r.int("score"))} ${t("ball")} · ${t(ago(r.str("completed_at")))}",
        translate = false,
        leading = { Ring(pct, 44.dp, if (passed) pal.green else pal.red) },
        trailing = { if (passed) TagGreen("Ötdi", Icons.Rounded.Check) else TagRed("Ötmadi", Icons.Rounded.Close) },
    )
}

@Composable
fun TxRow(tx: JSONObject) {
    val plus = tx.str("action") == "add"
    Row2(
        tx.str("reason").ifEmpty { tx.str("action_display") },
        listOf(t(tx.str("action_display")), t(ago(tx.str("created_at")))).filter { it.isNotEmpty() }.joinToString(" · "),
        translate = true,
        leading = { IcoBox(if (plus) Icons.Rounded.TrendingUp else Icons.Rounded.ShoppingBag, if (plus) pal.green else Color(0xFFEC4899)) },
        trailing = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Txt("${if (plus) "+" else "−"}${num(tx.int("amount"))}", weight = FontWeight.Bold, color = if (plus) pal.green else pal.red, translate = false)
                Spacer(Modifier.width(4.dp)); CoinDot(15.dp)
            }
        },
    )
}

@Composable
fun RankRow(s: JSONObject, coins: Boolean, highlight: Boolean = false) {
    val name = s.str("full_name").ifEmpty { s.str("username") }
    Row(
        Modifier.fillMaxWidth().then(if (highlight) Modifier.clip(RoundedCornerShape(12.dp)).background(pal.a1.copy(alpha = .15f)) else Modifier).padding(vertical = 8.dp, horizontal = if (highlight) 8.dp else 0.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Txt("#${num(s.int("rank"))}", Modifier.width(44.dp), weight = FontWeight.Bold, color = pal.muted, translate = false, lines = 1)
        Avatar(s.strOrNull("photo"), name, 34.dp)
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Txt(name, Modifier.weight(1f, false), weight = FontWeight.SemiBold, lines = 1, translate = false)
                if (s.bool("is_you")) { Spacer(Modifier.width(6.dp)); TagAccent("Siz") }
            }
            Muted("@${s.str("username")}", lines = 1, translate = false)
        }
        Spacer(Modifier.width(8.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Txt(num(s.int("value")), weight = FontWeight.Bold, translate = false)
            Spacer(Modifier.width(4.dp))
            if (coins) CoinDot(15.dp) else Muted("ball")
        }
    }
}
