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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONObject
import uz.itcacademy.parent.*
import uz.itcacademy.parent.ui.*

@Composable
fun HomeScreen() {
    val load = rememberChildLoad("")
    val parentName = AppState.parent?.str("first_name").orEmpty()
    Refreshable({ AppState.refresh(); load.retry() }) {
        Page {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Muted("${greeting()},", size = 14.sp)
                    Txt(parentName.ifEmpty { "Ota-ona" }, size = 27.sp, weight = FontWeight.Bold, spacing = (-.6).sp, lines = 1, translate = false)
                }
                Bell()
            }
            ChildSwitcher()
            if (AppState.children.isEmpty()) { NoChild(); return@Page }
            val d = load.data
            when {
                d == null && load.error != null -> ErrorState(load.error, load.retry)
                d == null -> SkeletonList(5, 110.dp)
                else -> HomeBody(d)
            }
        }
    }
}

@Composable
private fun HomeBody(d: JSONObject) {
    val p = pal
    val child = d.obj("child") ?: JSONObject()
    val prog = d.obj("progress") ?: JSONObject()
    val tests = d.obj("tests") ?: JSONObject()
    val att = d.obj("attendance") ?: JSONObject()
    val hw = d.obj("homework") ?: JSONObject()
    var idx = 0

    // Umumiy o'zlashtirish
    GlassCard(Modifier.reveal(idx++)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Ring(prog.int("percent"), 86.dp, p.a1, 17.sp)
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f)) {
                Txt("Özlaştiriş", size = 17.sp, weight = FontWeight.Bold)
                Muted(child.str("name"), lines = 1, translate = false)
                val courses = d.list("courses").joinToString(" · ") { it.str("name") }
                if (courses.isNotEmpty()) Muted(courses, lines = 2, translate = false)
                Muted("${prog.int("done")} / ${prog.int("total")} topşiriq bajarilgan")
            }
        }
        Spacer(Modifier.height(14.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MiniStat("${num(tests.dbl("avg"))}%", "Testlar", if (tests.int("taken") > 0) scoreColor(tests.dbl("avg")) else p.muted, Modifier.weight(1f))
            MiniStat("${att.int("display_rate")}%", att.str("display_label"), scoreColor(att.int("display_rate")), Modifier.weight(1f))
            MiniStat(if (hw.dbl("avg_grade") > 0) hw.dbl("avg_grade").toString() else "—", "Vazifa bahosi", p.a1, Modifier.weight(1f))
        }
    }

    // E'tibor bering
    val alerts = d.list("alerts")
    if (alerts.isNotEmpty()) Column(Modifier.reveal(idx++), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        alerts.forEach { a -> AlertRow(a) }
    } else Row(
        Modifier.reveal(idx++).fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(p.green.copy(alpha = .12f)).padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Rounded.Verified, null, Modifier.size(24.dp), p.green)
        Spacer(Modifier.width(12.dp))
        Column {
            Txt("Hammasi joyida", weight = FontWeight.SemiBold, color = p.green)
            Muted("Hozirça e'tibor talab qiladigan holat yöq")
        }
    }

    // Keyingi dars
    d.obj("schedule")?.obj("next")?.let { n ->
        GlassCard(Modifier.reveal(idx++).press { AppState.switchTab("attendance") }) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IcoBox(if (n.bool("is_now")) Icons.Rounded.Sensors else Icons.Rounded.Event, if (n.bool("is_now")) p.green else p.blue, 44.dp)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Muted(if (n.bool("is_now")) "Hozir darsda" else "Keyingi dars")
                    Txt("${if (n.bool("is_today")) "Bugun" else n.str("weekday")} · ${timeText(n.str("start"))}", size = 16.sp, weight = FontWeight.Bold)
                    Muted(listOf(n.str("course"), n.str("room"), n.str("teacher")).filter { it.isNotEmpty() }.joinToString(" · "), lines = 1, translate = false)
                }
                Icon(Icons.Rounded.ChevronRight, null, Modifier.size(22.dp), p.muted)
            }
        }
    }

    // To'lov holati
    d.obj("payment")?.let { pay -> PaymentMini(pay, Modifier.reveal(idx++)) }

    // Haftalik faollik
    val weekly = d.list("weekly")
    if (weekly.isNotEmpty()) GlassCard(Modifier.reveal(idx++)) {
        SectionTitle("Haftalik faollik", Icons.Rounded.BarChart)
        if (weekly.all { it.int("count") == 0 }) Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Rounded.Bedtime, null, Modifier.size(20.dp), p.muted)
            Spacer(Modifier.width(10.dp))
            Muted("Oxirgi 7 kunda video, vazifa yoki test faolligi bölmadi", size = 13.5.sp)
        } else ColumnChart(weekly.map { ChartPoint(it.str("label"), it.int("count"), it.bool("is_today")) })
    }

    // Yaqin muddatlar
    val deadlines = d.list("deadlines")
    if (deadlines.isNotEmpty()) GlassCard(Modifier.reveal(idx++)) {
        SectionTitle("Yaqinlaşayotgan vazifalar", Icons.Rounded.HourglassTop, "Barçasi") { AppState.studyTab = 1; AppState.switchTab("study") }
        deadlines.forEach { dl ->
            val c = levelColor(dl.str("level"))
            Row2(dl.str("title"), dl.str("course"), translate = false,
                leading = { IcoBox(Icons.Rounded.Assignment, c, 36.dp) },
                trailing = { Tag(if (dl.int("days_left") > 0) "${dl.int("days_left")} kun" else "${dl.int("hours_left")} soat", c, c.copy(alpha = .14f)) })
        }
    }

    // So'nggi faollik
    val act = d.list("activity")
    GlassCard(Modifier.reveal(idx++)) {
        SectionTitle("Söngi faollik", Icons.Rounded.History)
        if (act.isEmpty()) Muted("Hali faollik yöq")
        act.forEachIndexed { i, a ->
            if (i > 0) Hairline()
            val (ic, c) = kindStyle(a.str("type"))
            Row2(a.str("title"), "${a.str("text")} · ${ago(a.str("date"))}", translate = false, leading = { IcoBox(ic, c, 36.dp) })
        }
    }

    // Tezkor amallar
    Row(Modifier.reveal(idx), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Quick(Icons.Rounded.Forum, "Xabar yoziş", p.blue, Modifier.weight(1f)) { AppState.open(Route.Messages) }
        Quick(Icons.Rounded.EmojiEvents, "Yutuqlar", p.amber, Modifier.weight(1f)) { AppState.open(Route.Achievements) }
        Quick(Icons.Rounded.CalendarMonth, "Jadval", p.green, Modifier.weight(1f)) { AppState.switchTab("attendance") }
    }
}

@Composable
private fun MiniStat(value: String, label: String, color: Color, modifier: Modifier) {
    Column(modifier.clip(RoundedCornerShape(16.dp)).background(pal.surface).padding(vertical = 10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Txt(value, size = 18.sp, weight = FontWeight.Bold, color = color, lines = 1, translate = false)
        Muted(label, size = 11.5.sp, lines = 1)
    }
}

@Composable
fun AlertRow(a: JSONObject) {
    val c = levelColor(a.str("level"))
    val target = a.strOrNull("target")
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(c.copy(alpha = .12f))
            .then(if (target != null) Modifier.press { AppState.go(target) } else Modifier).padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(levelIcon(a.str("level")), null, Modifier.size(22.dp), c)
        Spacer(Modifier.width(12.dp))
        Txt(a.str("text"), Modifier.weight(1f), 14.sp, FontWeight.Medium)
        if (target != null) Icon(Icons.Rounded.ChevronRight, null, Modifier.size(20.dp), c)
    }
}

/** To'lov holati qisqa kartasi (bosh sahifa va farzandlar ro'yxatida). */
@Composable
fun PaymentMini(pay: JSONObject, modifier: Modifier = Modifier) {
    val p = pal
    val state = pay.str("state")
    val (c, title, sub) = paymentState(pay)
    GlassCard(modifier.press { AppState.switchTab("payments") }) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IcoBox(Icons.Rounded.AccountBalanceWallet, c, 44.dp)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Muted("Tölov")
                Txt(title, size = 16.sp, weight = FontWeight.Bold, color = if (state in listOf("overdue", "blocked")) c else p.text)
                if (sub.isNotEmpty()) Muted(sub, lines = 1)
            }
            if (state in listOf("soon", "overdue", "blocked")) Btn("Tölaş", small = true, kind = BtnKind.Primary) { AppState.switchTab("payments") }
            else Icon(Icons.Rounded.ChevronRight, null, Modifier.size(22.dp), p.muted)
        }
    }
}

@Composable
fun paymentState(pay: JSONObject): Triple<Color, String, String> {
    val p = pal
    val days = pay.intOrNull("days_left")
    val fee = pay.intOrNull("fee")
    val next = pay.strOrNull("next_date")
    return when (pay.str("state")) {
        "contract" -> Triple(p.blue, "Şartnoma asosida", pay.str("contract_name"))
        "blocked" -> Triple(p.red, "Muddat ötgan — kiriş bloklangan", fee?.let { som(it) } ?: "")
        "overdue" -> Triple(p.red, "Tölov muddati ötgan", next?.let { "Muddat: ${dateText(it)}" } ?: "")
        "soon" -> Triple(p.amber, "Tölovga $days kun qoldi", listOfNotNull(next?.let { dateText(it) }, fee?.let { som(it) }).joinToString(" · "))
        "ok" -> Triple(p.green, "Tölangan", next?.let { "Keyingi tölov: ${dateText(it)}" } ?: "")
        else -> Triple(p.muted, "Ma'lumot yöq", "")
    }
}

@Composable
private fun Quick(icon: ImageVector, label: String, color: Color, modifier: Modifier, onClick: () -> Unit) {
    Column(modifier.card(RoundedCornerShape(20.dp)).press(onClick = onClick).padding(vertical = 14.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        IcoBox(icon, color, 42.dp)
        Spacer(Modifier.height(8.dp))
        Txt(label, size = 12.5.sp, weight = FontWeight.SemiBold, lines = 1)
    }
}
