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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import org.json.JSONObject
import uz.itcacademy.lms.*
import uz.itcacademy.lms.ui.*

fun Api.rowsOf(o: JSONObject, key: String): List<JSONObject> {
    val a = o.optJSONArray(key) ?: return emptyList()
    return (0 until a.length()).mapNotNull { a.optJSONObject(it) }
}

@Composable
fun RatingScreen() {
    var tab by remember { mutableIntStateOf(0) }
    var profession by remember { mutableStateOf("") }
    var q by remember { mutableStateOf("") }
    var query by remember { mutableStateOf("") }
    LaunchedEffect(q) { delay(350); query = q.trim() }
    val key = if (tab == 0) "coins" else "score"
    val load = rememberLoad(key, profession, query) {
        Api.get("/api/v1/reyting/", mapOf("tab" to key, "profession" to profession, "q" to query, "limit" to 100))
    }
    Page {
        H1("Reyting", "Eng faol öquvçilar — coin yoki uy vazifasi ballari böyiça", Modifier.reveal(0))
        Segmented(listOf("Coinlar", "Ballar"), tab, Modifier.reveal(1)) { tab = it }
        Field(q, { q = it }, "Ism yoki login böyiça qidiriş", Modifier.reveal(2), Icons.Rounded.Search)
        val d = load.data
        if (d != null) {
            val profs = Api.rowsOf(d, "professions")
            if (profs.isNotEmpty()) Chips(
                listOf("" to "Barça kurslar") + profs.map { it.int("id").toString() to it.str("name") }, profession, Modifier.reveal(3),
            ) { profession = it }
        }
        when {
            load.error != null -> ErrorState(load.error, load.retry)
            d == null -> SkeletonList(6)
            else -> {
                val list = Api.rowsOf(d, "students")
                val searching = query.isNotEmpty()
                val coins = tab == 0
                if (list.isEmpty()) EmptyState(Icons.Rounded.EmojiEvents, "Hech kim topilmadi", "Qidiruv yoki filtrni özgartirib köring.")
                else {
                    val rank = d.int("user_rank")
                    if (rank > 0 && !searching) {
                        val above = list.firstOrNull { it.int("rank") == rank - 1 }
                        val gap = above?.let { (it.int("value") - d.int("user_value") + 1).coerceAtLeast(1) }
                        val total = d.int("total")
                        Row(
                            Modifier.reveal(4).fillMaxWidth().card(fill = pal.a1.copy(alpha = .16f)).padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Txt("#${num(rank)}", size = 30.sp, weight = FontWeight.ExtraBold, spacing = (-1).sp, translate = false)
                            Spacer(Modifier.width(14.dp))
                            Column(Modifier.weight(1f)) {
                                Txt("Sizning öriningiz", weight = FontWeight.Bold)
                                if (total > 0) Muted("${t("jami")} ${num(total)} ${t("öquvçi")}", translate = false)
                            }
                            Column(horizontalAlignment = Alignment.End) {
                                Txt(num(d.int("user_value")), size = 18.sp, weight = FontWeight.Bold, translate = false)
                                if (rank == 1) Muted("Lider") else if (gap != null) Muted("#${num(rank - 1)}: +${num(gap)}", translate = false)
                            }
                        }
                    }
                    val top = if (searching) emptyList() else list.take(3)
                    val rest = if (searching) list else list.drop(3)
                    if (top.size == 3) Row(Modifier.reveal(5).fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Bottom) {
                        Podium(top[1], 2, coins, Modifier.weight(1f))
                        Podium(top[0], 1, coins, Modifier.weight(1.15f))
                        Podium(top[2], 3, coins, Modifier.weight(1f))
                    }
                    if ((if (top.size == 3) rest else list).isNotEmpty()) GlassCard(Modifier.reveal(6).fillMaxWidth(), 12.dp) {
                        (if (top.size == 3) rest else list).forEach { s -> key(s.int("rank"), s.str("username")) { RankRow(s, coins, s.bool("is_you")) } }
                    }
                }
            }
        }
    }
}

@Composable
private fun Podium(s: JSONObject, place: Int, coins: Boolean, modifier: Modifier) {
    val color = when (place) { 1 -> Color(0xFFFBBF24); 2 -> Color(0xFFCBD5E1); else -> Color(0xFFD97706) }
    val name = s.str("full_name").ifEmpty { s.str("username") }
    Column(
        modifier.clip(RoundedCornerShape(20.dp)).background(Brush.verticalGradient(listOf(color.copy(alpha = .22f), pal.surface))).card(RoundedCornerShape(20.dp), Color.Transparent)
            .padding(top = if (place == 1) 20.dp else 12.dp, bottom = 12.dp, start = 6.dp, end = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        if (place == 1) Icon(Icons.Rounded.WorkspacePremium, null, Modifier.size(22.dp), color)
        Avatar(s.strOrNull("photo"), name, if (place == 1) 64.dp else 50.dp, color)
        Spacer(Modifier.height(6.dp))
        Txt(name, size = 12.5.sp, weight = FontWeight.SemiBold, lines = 1, align = TextAlign.Center, translate = false)
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 3.dp)) {
            if (coins) { CoinDot(14.dp); Spacer(Modifier.width(3.dp)) }
            Txt(num(s.int("value")), size = 13.5.sp, weight = FontWeight.Bold, translate = false, lines = 1)
        }
        if (s.bool("is_you")) { Spacer(Modifier.height(4.dp)); TagAccent("Siz") }
    }
}

@Composable
fun ResultsScreen() {
    val ctx = LocalContext.current
    var tab by remember { mutableIntStateOf(0) }
    var filter by remember { mutableStateOf("") }
    var q by remember { mutableStateOf("") }
    val tests = rememberLoad { Api.getAll("/api/v1/my/test-results/") }
    val certs = rememberLoad { Api.getAll("/api/v1/my/certificates/") }
    Page(bottom = 40.dp) {
        BackHeader("Natijalar", "Test natijalaringiz va olgan sertifikatlaringiz", { AppState.back() })
        Segmented(listOf("Testlar", "Sertifikatlar"), tab) { tab = it }
        if (tab == 0) {
            val list = tests.data
            when {
                tests.error != null -> ErrorState(tests.error, tests.retry)
                list == null -> SkeletonList(6)
                list.isEmpty() -> EmptyState(Icons.Rounded.TaskAlt, "Hali test topşirmagansiz", "Darslardagi testlarni yeçganingizdan keyin natijalar şu yerda paydo böladi.")
                else -> {
                    val passed = list.count { it.bool("passed") }
                    val avg = list.sumOf { r -> val tq = r.int("total_questions"); if (tq > 0) r.int("correct_answers") * 100 / tq else 0 } / list.size
                    Row(Modifier.reveal(0), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        MiniStat(num(list.size), "Jami testlar", Modifier.weight(1f))
                        MiniStat(num(passed), "Muvaffaqiyatli", Modifier.weight(1f))
                        MiniStat("$avg%", "Ortaça natija", Modifier.weight(1f))
                    }
                    Chips(listOf("" to "Barçasi", "1" to "Ötdi", "0" to "Ötmadi"), filter, Modifier.reveal(1)) { filter = it }
                    Field(q, { q = it }, "Test nomi böyiça qidiriş", Modifier.reveal(2), Icons.Rounded.Search)
                    val shown = list.filter { (filter.isEmpty() || (it.bool("passed") == (filter == "1"))) && it.str("test_name").contains(q.trim(), true) }
                    GlassCard(Modifier.reveal(3).fillMaxWidth(), 14.dp) {
                        if (shown.isEmpty()) Muted("Mos natija topilmadi", Modifier.padding(16.dp))
                        shown.forEach { ResultRow(it) }
                    }
                }
            }
        } else {
            val list = certs.data
            when {
                certs.error != null -> ErrorState(certs.error, certs.retry)
                list == null -> SkeletonList(3, 150.dp)
                list.isEmpty() -> EmptyState(Icons.Rounded.WorkspacePremium, "Hali sertifikat yöq", "Kursni muvaffaqiyatli tugatganingizdan söng sertifikat şu yerda paydo böladi.")
                else -> list.forEachIndexed { i, c ->
                    GlassCard(Modifier.reveal(i).fillMaxWidth(), fill = pal.a1.copy(alpha = .13f)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Tinted(Color(0xFFF97316), Modifier.size(44.dp), RoundedCornerShape(22.dp)) { Icon(Icons.Rounded.WorkspacePremium, null, Modifier.size(22.dp), Color.White) }
                            Spacer(Modifier.weight(1f))
                            when (c.str("status")) {
                                "active" -> TagGreen("Amalda")
                                "expired" -> TagAmber("Muddati ötgan")
                                "frozen" -> TagBlue("Muzlatilgan")
                                "revoked" -> TagRed("Bekor qilingan")
                                else -> Tag(c.str("status"))
                            }
                        }
                        Spacer(Modifier.height(12.dp))
                        Muted("Sertifikat")
                        Txt(c.str("profession_name"), size = 17.sp, weight = FontWeight.Bold, translate = false)
                        Muted("ID: ${c.str("certificate_id")}", Modifier.padding(top = 6.dp), translate = false)
                        Muted("${t("Berilgan")}: ${dateText(c.strOrNull("valid_from") ?: c.str("issued_at"))}", translate = false)
                        c.strOrNull("file")?.let { f ->
                            Spacer(Modifier.height(10.dp))
                            Btn("PDF ni oçiş", small = true, icon = Icons.Rounded.Download) {
                                openBrowser(ctx, if (f.startsWith("http")) f else Api.SITE + if (f.startsWith("/")) f else "/media/$f")
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun MiniStat(value: String, label: String, modifier: Modifier = Modifier) {
    Column(modifier.card(RoundedCornerShape(18.dp)).padding(12.dp)) {
        Txt(value, size = 21.sp, weight = FontWeight.Bold, translate = false, lines = 1)
        Muted(label, size = 11.5.sp, lines = 2)
    }
}
