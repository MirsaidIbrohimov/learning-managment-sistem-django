package uz.itcacademy.parent.screens

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONObject
import uz.itcacademy.parent.*
import uz.itcacademy.parent.ui.*

@Composable
fun statusColor(status: String?): Color {
    val p = pal
    return when (status) {
        "present" -> p.green
        "late" -> p.amber
        "absent" -> p.red
        "sick" -> p.blue
        "excused" -> p.a2
        "visited" -> p.text.copy(alpha = .3f)
        else -> p.surface2
    }
}

fun statusLabel(status: String?) = when (status) {
    "present" -> "Kelgan"
    "late" -> "Keçikkan"
    "absent" -> "Kelmagan"
    "sick" -> "Kasal"
    "excused" -> "Sabab bilan"
    "visited" -> "Platformaga kirgan"
    else -> "Ma'lumot yöq"
}

@Composable
fun AttendanceScreen() {
    val load = rememberChildLoad("attendance/")
    Refreshable({ load.retry() }) {
        Page {
            TabHeader("Davomat", AppState.child?.str("name"))
            if (AppState.children.isEmpty()) { NoChild(); return@Page }
            val d = load.data
            when {
                d == null && load.error != null -> ErrorState(load.error, load.retry)
                d == null -> SkeletonList(4, 120.dp)
                else -> AttendanceBody(d)
            }
        }
    }
}

@Composable
private fun AttendanceBody(d: JSONObject) {
    val p = pal
    val a = d.obj("attendance") ?: JSONObject()
    GlassCard(Modifier.reveal(0)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Ring(a.int("display_rate"), 80.dp, scoreColor(a.int("display_rate")), 16.sp)
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f)) {
                Txt(a.str("display_label"), size = 17.sp, weight = FontWeight.Bold)
                Muted("Oxirgi ${a.int("days")} kun")
                Muted("Platformaga ${a.int("active_days")} kun kirgan")
            }
        }
        if (a.int("total") > 0) {
            Spacer(Modifier.height(14.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf("present", "late", "absent", "sick", "excused").forEach { s ->
                    val c = statusColor(s)
                    Column(Modifier.weight(1f).clip(RoundedCornerShape(14.dp)).background(c.copy(alpha = .12f)).padding(vertical = 8.dp),
                        horizontalAlignment = Alignment.CenterHorizontally) {
                        Txt("${a.int(s)}", size = 17.sp, weight = FontWeight.Bold, color = c)
                        Muted(statusLabel(s), size = 10.sp, lines = 1)
                    }
                }
            }
        }
    }

    d.obj("calendar")?.let { Calendar(it, Modifier.reveal(1)) }

    d.obj("schedule")?.let { s ->
        GlassCard(Modifier.reveal(2)) {
            SectionTitle("Dars jadvali", Icons.Rounded.CalendarMonth)
            val groups = s.list("groups")
            if (groups.isEmpty()) Muted("Farzandingiz hali guruhga biriktirilmagan")
            s.list("week").forEach { day ->
                val items = day.list("items")
                if (items.isEmpty()) return@forEach
                val today = day.bool("is_today")
                Row(Modifier.padding(vertical = 6.dp), verticalAlignment = Alignment.Top) {
                    Box(
                        Modifier.width(46.dp).clip(RoundedCornerShape(12.dp)).background(if (today) p.a1 else p.surface2).padding(vertical = 8.dp),
                        contentAlignment = Alignment.Center,
                    ) { Txt(day.str("short"), size = 13.sp, weight = FontWeight.Bold, color = if (today) Color.White else p.text, translate = false) }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        items.forEach { g ->
                            Column {
                                Txt("${g.str("time")} · ${g.str("course")}", weight = FontWeight.SemiBold, translate = false)
                                Muted(listOf(g.str("name"), g.str("room"), g.str("teacher")).filter { it.isNotEmpty() }.joinToString(" · "), translate = false)
                            }
                        }
                    }
                }
            }
        }
    }

    val recent = a.list("recent")
    if (recent.isNotEmpty()) GlassCard(Modifier.reveal(3)) {
        SectionTitle("Söngi darslar", Icons.Rounded.History)
        recent.forEachIndexed { i, r ->
            if (i > 0) Hairline()
            val c = statusColor(r.str("status"))
            Row2(
                "${dateText(r.str("date"))} · ${r.str("label")}",
                listOfNotNull(r.str("group").takeIf { it.isNotEmpty() }, r.strOrNull("visited_at")?.let { "Saytga kirgan: ${timeText(it)}" }, r.str("note").takeIf { it.isNotEmpty() }).joinToString(" · "),
                translate = false,
                leading = { Box(Modifier.size(12.dp).clip(RoundedCornerShape(4.dp)).background(c)) },
            )
        }
    }
}

/** 6 haftalik kalendar: qatorlar — hafta kunlari, ustunlar — haftalar. Kun bosilsa tafsiloti chiqadi. */
@Composable
private fun Calendar(cal: JSONObject, modifier: Modifier) {
    val p = pal
    var sel by remember { mutableStateOf<JSONObject?>(null) }
    GlassCard(modifier) {
        SectionTitle("Kalendar", Icons.Rounded.CalendarViewMonth)
        cal.list("rows").forEach { row ->
            Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                Muted(row.str("label"), Modifier.width(28.dp), 11.5.sp, translate = false)
                row.list("cells").forEach { c ->
                    val status = c.strOrNull("status")
                    val chosen = sel?.str("date") == c.str("date")
                    val bg by animateColorAsState(if (c.bool("future")) Color.Transparent else statusColor(status), label = "cell")
                    Box(
                        Modifier.weight(1f).padding(horizontal = 3.dp).aspectRatio(1f).clip(RoundedCornerShape(8.dp)).background(bg)
                            .then(if (c.bool("today") || chosen) Modifier.border(2.dp, if (chosen) p.text else p.a1, RoundedCornerShape(8.dp)) else Modifier)
                            .press(!c.bool("future"), scale = .85f) { sel = c },
                    )
                }
            }
        }
        Spacer(Modifier.height(10.dp))
        val s = sel
        if (s != null) Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(p.surface).padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(Modifier.size(14.dp).clip(RoundedCornerShape(4.dp)).background(statusColor(s.strOrNull("status"))))
            Spacer(Modifier.width(10.dp))
            Column {
                Txt(dateText(s.str("date")), weight = FontWeight.SemiBold)
                Muted(statusLabel(s.strOrNull("status")) + (s.strOrNull("visited_at")?.let { " · saytga ${timeText(it)} da kirgan" } ?: ""))
            }
        } else FlowRowLegend()
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun FlowRowLegend() {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        listOf("present", "late", "absent", "sick", "excused", "visited").forEach { s ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(10.dp).clip(RoundedCornerShape(3.dp)).background(statusColor(s)))
                Spacer(Modifier.width(5.dp))
                Muted(statusLabel(s), size = 11.5.sp)
            }
        }
    }
}
