package uz.itcacademy.parent.screens

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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import org.json.JSONObject
import uz.itcacademy.parent.*
import uz.itcacademy.parent.ui.*

private fun badgeIcon(name: String): ImageVector = when (name) {
    "pencil-square" -> Icons.Rounded.EditNote
    "check2-all" -> Icons.Rounded.DoneAll
    "trophy-fill" -> Icons.Rounded.EmojiEvents
    "star-fill" -> Icons.Rounded.Star
    "patch-check-fill" -> Icons.Rounded.WorkspacePremium
    "coin" -> Icons.Rounded.Toll
    "fire" -> Icons.Rounded.LocalFireDepartment
    else -> Icons.Rounded.MilitaryTech
}

private fun hexColor(s: String, fallback: Color): Color =
    runCatching { Color(android.graphics.Color.parseColor(s)) }.getOrDefault(fallback)

@Composable
fun AchievementsScreen() {
    val load = rememberChildLoad("achievements/")
    Refreshable({ load.retry() }) {
        Page {
            BackHeader("Yutuqlar", AppState.child?.str("name"), onBack = { AppState.back() })
            if (AppState.children.size > 1) ChildSwitcher()
            if (AppState.children.isEmpty()) { NoChild(); return@Page }
            val d = load.data
            when {
                d == null && load.error != null -> ErrorState(load.error, load.retry)
                d == null -> SkeletonList(4, 100.dp)
                else -> AchievementsBody(d)
            }
        }
    }
}

@Composable
private fun AchievementsBody(d: JSONObject) {
    val p = pal
    val rank = d.obj("ranking") ?: JSONObject()
    Row(Modifier.reveal(0), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Stat(Icons.Rounded.Leaderboard, p.a1, "${rank.int("position")} / ${rank.int("total")}", "Umumiy reyting", Modifier.weight(1f))
        Stat(Icons.Rounded.LocalFireDepartment, p.amber, "${d.int("streak")} kun", "Ketma-ket faol", Modifier.weight(1f))
        Stat(Icons.Rounded.Toll, p.green, num(d.int("coins_earned")), "Yiğilgan coin", Modifier.weight(1f))
    }

    val badges = d.list("badges")
    GlassCard(Modifier.reveal(1)) {
        SectionTitle("Nişonlar · ${d.int("earned_count")} / ${badges.size}", Icons.Rounded.MilitaryTech)
        badges.chunked(3).forEach { row ->
            Row(Modifier.padding(vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                row.forEach { b ->
                    val earned = b.bool("earned")
                    val c = hexColor(b.str("color"), p.a1)
                    Column(Modifier.weight(1f).graphicsLayer { alpha = if (earned) 1f else .38f }, horizontalAlignment = Alignment.CenterHorizontally) {
                        Box(Modifier.size(58.dp).clip(RoundedCornerShape(20.dp)).background(if (earned) c.copy(alpha = .2f) else p.surface2),
                            contentAlignment = Alignment.Center) {
                            Icon(if (earned) badgeIcon(b.str("icon")) else Icons.Rounded.Lock, null, Modifier.size(28.dp), if (earned) c else p.muted)
                        }
                        Spacer(Modifier.height(6.dp))
                        Txt(b.str("title"), size = 12.sp, weight = FontWeight.SemiBold, align = TextAlign.Center, lines = 2)
                        Muted(b.str("description"), size = 10.5.sp, lines = 2)
                    }
                }
                repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
    }

    val ranks = d.list("course_ranks")
    if (ranks.isNotEmpty()) GlassCard(Modifier.reveal(2)) {
        SectionTitle("Kurs böyiça örni", Icons.Rounded.Groups)
        ranks.forEachIndexed { i, r ->
            if (i > 0) Hairline()
            val score = r.obj("score")
            val coins = r.obj("coins")
            Column(Modifier.padding(vertical = 10.dp)) {
                Txt(r.str("course"), weight = FontWeight.SemiBold, translate = false)
                Spacer(Modifier.height(6.dp))
                if (score != null) {
                    Muted("Ball böyiça: ${score.int("position")}-örin (${score.int("total")} ta öquvçi) · ${num(score.dbl("value"))} ball")
                    ProgressBar(score.int("beat") / 100f, Modifier.padding(vertical = 5.dp), color = p.green, height = 6.dp)
                    Muted("${score.int("beat")}% öquvçidan oldinda", size = 11.5.sp)
                }
                if (coins != null) Muted("Coin böyiça: ${coins.int("position")}-örin · ${num(coins.int("value"))} coin", Modifier.padding(top = 4.dp))
            }
        }
    }

    val certs = d.list("certificates")
    GlassCard(Modifier.reveal(3)) {
        SectionTitle("Sertifikatlar", Icons.Rounded.WorkspacePremium)
        if (certs.isEmpty()) Muted("Hali sertifikat yöq. Kursni tugatgaç sertifikat beriladi.")
        certs.forEachIndexed { i, c ->
            if (i > 0) Hairline()
            Row2(c.str("course"), "№ ${c.str("certificate_id")} · ${dateText(c.str("issued_at"))}", translate = false,
                leading = { IcoBox(Icons.Rounded.WorkspacePremium, p.amber, 40.dp) },
                trailing = {
                    if (c.str("status") == "active") TagGreen(c.str("status_label")) else TagAmber(c.str("status_label"))
                })
        }
    }
}

// ───────── Kitoblar ─────────
@Composable
fun BooksScreen() {
    val load = rememberChildLoad("books/")
    val p = pal
    Refreshable({ load.retry() }) {
        Page {
            BackHeader("Kitoblar", AppState.child?.str("name"), onBack = { AppState.back() })
            if (AppState.children.size > 1) ChildSwitcher()
            if (AppState.children.isEmpty()) { NoChild(); return@Page }
            val d = load.data
            when {
                d == null && load.error != null -> ErrorState(load.error, load.retry)
                d == null -> SkeletonList(3, 90.dp)
                else -> {
                    val active = d.list("active")
                    val returned = d.list("returned")
                    if (active.isEmpty() && returned.isEmpty()) EmptyState(Icons.Rounded.LocalLibrary, "Kitob olinmagan", "Farzandingiz kutubxonadan kitob olsa, şu yerda körinadi")
                    if (active.isNotEmpty()) SectionTitle("Hozir qölida", Icons.Rounded.MenuBook)
                    active.forEachIndexed { i, b ->
                        val left = b.intOrNull("days_left") ?: 0
                        val c = when { left < 0 -> p.red; left <= 3 -> p.amber; else -> p.green }
                        BookRow(b, Modifier.reveal(i)) {
                            Tag(if (left < 0) "${-left} kun keçikdi" else "$left kun qoldi", c, c.copy(alpha = .14f))
                        }
                    }
                    if (returned.isNotEmpty()) SectionTitle("Qaytarilgan", Icons.Rounded.AssignmentReturned)
                    returned.forEachIndexed { i, b ->
                        BookRow(b, Modifier.reveal(active.size + i)) { TagGreen("Qaytarildi") }
                    }
                }
            }
        }
    }
}

@Composable
private fun BookRow(b: JSONObject, modifier: Modifier, tag: @Composable () -> Unit) {
    val p = pal
    Row(modifier.fillMaxWidth().card(RoundedCornerShape(18.dp)).padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(48.dp, 64.dp).clip(RoundedCornerShape(10.dp)).background(p.surface2), contentAlignment = Alignment.Center) {
            Icon(Icons.Rounded.Book, null, Modifier.size(24.dp), p.muted)
            Api.media(b.strOrNull("cover"))?.let { AsyncImage(it, null, Modifier.fillMaxSize(), contentScale = androidx.compose.ui.layout.ContentScale.Crop) }
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Txt(b.str("title"), weight = FontWeight.SemiBold, lines = 2, translate = false)
            Muted(b.str("author"), lines = 1, translate = false)
            Muted("Berilgan: ${dateText(b.str("given"))} · Qaytariş: ${dateText(b.str("return_date"))}", size = 11.5.sp)
        }
        Spacer(Modifier.width(8.dp))
        tag()
    }
}
