package uz.itcacademy.parent.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.Icon
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONObject
import uz.itcacademy.parent.*
import uz.itcacademy.parent.ui.*

@Composable
fun StudyScreen() {
    val parts = listOf("lessons/", "homework/", "tests/")
    val load = rememberChildLoad(parts[AppState.studyTab])
    Refreshable({ load.retry() }) {
        Page {
            TabHeader("Öqiş", AppState.child?.str("name"))
            if (AppState.children.isEmpty()) { NoChild(); return@Page }
            Segmented(listOf("Darslar", "Vazifalar", "Testlar"), AppState.studyTab) { AppState.studyTab = it }
            val d = load.data
            when {
                d == null && load.error != null -> ErrorState(load.error, load.retry)
                d == null -> SkeletonList(5, 80.dp)
                AppState.studyTab == 0 -> LessonsTab(d)
                AppState.studyTab == 1 -> HomeworkTab(d)
                else -> TestsTab(d)
            }
        }
    }
}

// ───────── Darslar ─────────
@Composable
private fun LessonsTab(d: JSONObject) {
    val courses = d.list("courses")
    if (courses.isEmpty()) { EmptyState(Icons.Rounded.School, "Kurs yöq", "Farzandingiz hali birorta kursga yozilmagan"); return }
    courses.forEachIndexed { i, c ->
        GlassCard(Modifier.reveal(i)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Ring(c.int("percent"), 54.dp)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Txt(c.str("name"), size = 16.sp, weight = FontWeight.Bold, translate = false)
                    Muted("${c.int("done")} / ${c.int("total")} dars bajarilgan")
                }
            }
            Spacer(Modifier.height(10.dp))
            val sections = c.list("sections")
            if (sections.isEmpty()) Muted("Bu kursda hali kuzatiladigan darslar yöq")
            sections.forEach { s -> SectionBlock(s) }
        }
    }
}

@Composable
private fun SectionBlock(s: JSONObject) {
    val p = pal
    var open by rememberSaveable(s.int("id")) { mutableStateOf(false) }
    val rot by animateFloatAsState(if (open) 90f else 0f, label = "rot")
    Column(Modifier.padding(top = 6.dp).clip(RoundedCornerShape(16.dp)).background(p.surface)) {
        Row(Modifier.fillMaxWidth().press(scale = .99f) { open = !open }.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Rounded.ChevronRight, null, Modifier.size(20.dp).graphicsLayer { rotationZ = rot }, p.muted)
            Spacer(Modifier.width(6.dp))
            Column(Modifier.weight(1f)) {
                Txt(s.str("title"), weight = FontWeight.SemiBold, lines = 2, translate = false)
                ProgressBar(s.int("percent") / 100f, Modifier.padding(top = 6.dp), height = 5.dp)
            }
            Spacer(Modifier.width(10.dp))
            Muted("${s.int("done")}/${s.int("total")}")
        }
        AnimatedVisibility(open, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
            Column(Modifier.padding(start = 12.dp, end = 12.dp, bottom = 8.dp)) {
                s.list("items").forEach { it ->
                    val (ic, c) = when (it.str("type")) {
                        "video" -> Icons.Rounded.PlayCircle to p.blue
                        "homework" -> Icons.Rounded.Assignment to p.a1
                        "test" -> Icons.Rounded.Quiz to p.amber
                        "speaking" -> Icons.Rounded.Mic to p.a2
                        else -> Icons.Rounded.Article to p.muted
                    }
                    Row2(it.str("title"), it.str("detail"), translate = false,
                        leading = { IcoBox(ic, c, 32.dp) },
                        trailing = {
                            if (it.bool("done")) Icon(Icons.Rounded.CheckCircle, "Bajarilgan", Modifier.size(22.dp), p.green)
                            else Icon(Icons.Rounded.RadioButtonUnchecked, "Bajarilmagan", Modifier.size(22.dp), p.muted)
                        })
                }
            }
        }
    }
}

// ───────── Vazifalar ─────────
@Composable
private fun HomeworkTab(d: JSONObject) {
    val p = pal
    val counts = d.obj("counts") ?: JSONObject()
    val sum = d.obj("summary") ?: JSONObject()
    var filter by rememberSaveable { mutableStateOf("all") }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Stat(Icons.Rounded.TaskAlt, p.green, "${counts.int("submitted")}", "Topşirilgan", Modifier.weight(1f))
        Stat(Icons.Rounded.PendingActions, p.blue, "${counts.int("todo")}", "Kutilmoqda", Modifier.weight(1f))
        Stat(Icons.Rounded.EventBusy, p.red, "${counts.int("missed")}", "Qoldirilgan", Modifier.weight(1f))
    }
    if (sum.dbl("avg_grade") > 0) Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(p.a1.copy(alpha = .12f)).padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Rounded.Grade, null, Modifier.size(22.dp), p.a1)
        Spacer(Modifier.width(10.dp))
        Txt("Örtaça baho: ${sum.dbl("avg_grade")} / 10", weight = FontWeight.SemiBold)
    }
    Chips(listOf("all" to "Hammasi", "done" to "Baholangan", "submitted" to "Tekşiruvda", "todo" to "Topşirilmagan", "missed" to "Qoldirilgan"), filter) { filter = it }
    val rows = d.list("rows").filter {
        when (filter) {
            "all" -> true
            "missed" -> it.str("state") in listOf("missed", "late")
            else -> it.str("state") == filter
        }
    }
    if (rows.isEmpty()) EmptyState(Icons.Rounded.Assignment, "Vazifa yöq", "Bu bölimda hozirça vazifa topilmadi")
    rows.forEachIndexed { i, r -> HomeworkCard(r, Modifier.reveal(i)) }
}

@Composable
private fun HomeworkCard(r: JSONObject, modifier: Modifier) {
    val p = pal
    val sub = r.obj("submission")
    val (label, c) = when (r.str("state")) {
        "done" -> "Baholangan" to p.green
        "submitted" -> (sub?.str("label") ?: "Tekşiruvda") to p.blue
        "late" -> "Keç topşirilgan" to p.amber
        "missed" -> "Topşirilmagan" to p.red
        else -> "Kutilmoqda" to p.muted
    }
    GlassCard(modifier, pad = 14.dp) {
        Row(verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                Txt(r.str("title"), weight = FontWeight.SemiBold, translate = false)
                Muted(r.str("course"), lines = 1, translate = false)
            }
            Spacer(Modifier.width(8.dp))
            Tag(label, c, c.copy(alpha = .14f))
        }
        Spacer(Modifier.height(8.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            r.strOrNull("due")?.let {
                Icon(Icons.Rounded.Schedule, null, Modifier.size(15.dp), p.muted)
                Spacer(Modifier.width(4.dp))
                Muted("Muddat: ${dateText(it)} ${timeText(it)}")
                Spacer(Modifier.width(12.dp))
            }
            sub?.intOrNull("grade")?.let { g ->
                Spacer(Modifier.weight(1f))
                Txt("$g / ${r.int("max_score")}", size = 16.sp, weight = FontWeight.Bold, color = scoreColor(g * 100.0 / r.int("max_score").coerceAtLeast(1)))
            }
        }
        sub?.strOrNull("feedback")?.let { fb ->
            Spacer(Modifier.height(8.dp))
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(p.surface).padding(10.dp)) {
                Icon(Icons.Rounded.FormatQuote, null, Modifier.size(18.dp), p.a1)
                Spacer(Modifier.width(6.dp))
                Txt(fb, size = 13.5.sp, color = p.text2, translate = false)
            }
        }
    }
}

// ───────── Testlar ─────────
@Composable
private fun TestsTab(d: JSONObject) {
    val p = pal
    val s = d.obj("summary") ?: JSONObject()
    val dist = d.obj("dist") ?: JSONObject()
    GlassCard(Modifier.reveal(0)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Ring(s.dbl("avg").toInt(), 80.dp, scoreColor(s.dbl("avg")), 16.sp)
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Txt("Örtaça ball", size = 16.sp, weight = FontWeight.Bold)
                Row(verticalAlignment = Alignment.CenterVertically) { Dot(p.green); Spacer(Modifier.width(6.dp)); Muted("Ötdi: ${s.int("passed")}") }
                Row(verticalAlignment = Alignment.CenterVertically) { Dot(p.red); Spacer(Modifier.width(6.dp)); Muted("Ötmadi: ${s.int("failed")}") }
                Row(verticalAlignment = Alignment.CenterVertically) { Dot(p.a1); Spacer(Modifier.width(6.dp)); Muted("Eng yaxşi: ${d.int("best")}%") }
            }
        }
        val total = (dist.int("excellent") + dist.int("good") + dist.int("poor")).coerceAtLeast(1)
        if (s.int("taken") > 0) {
            Spacer(Modifier.height(14.dp))
            Row(Modifier.fillMaxWidth().height(10.dp).clip(RoundedCornerShape(5.dp))) {
                listOf(dist.int("excellent") to p.green, dist.int("good") to p.amber, dist.int("poor") to p.red).forEach { (n, c) ->
                    if (n > 0) Box(Modifier.weight(n.toFloat() / total).fillMaxHeight().background(c))
                }
            }
            Spacer(Modifier.height(6.dp))
            Muted("80%+ : ${dist.int("excellent")}   ·   60–79% : ${dist.int("good")}   ·   60% dan past : ${dist.int("poor")}", size = 11.5.sp)
        }
    }
    val sp = d.obj("speaking")
    if (sp != null && sp.int("count") > 0) Row2(
        "Speaking topşiriqlari", "${sp.int("count")} ta · baholangan: ${sp.int("graded")} · örtaça: ${sp.dbl("avg_grade")}",
        Modifier.reveal(1).card().padding(horizontal = 14.dp),
        leading = { IcoBox(Icons.Rounded.RecordVoiceOver, p.a2, 36.dp) },
    )
    val rows = d.list("rows")
    if (rows.isEmpty()) EmptyState(Icons.Rounded.Quiz, "Test natijasi yöq", "Farzandingiz test topşirgaç, natijalar şu yerda körinadi")
    rows.forEachIndexed { i, r ->
        val c = scoreColor(r.int("score"))
        Row(
            Modifier.reveal(i + 2).fillMaxWidth().card(RoundedCornerShape(18.dp)).padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(Modifier.size(52.dp).clip(RoundedCornerShape(16.dp)).background(c.copy(alpha = .14f)), contentAlignment = Alignment.Center) {
                Txt("${r.int("score")}%", size = 14.sp, weight = FontWeight.Bold, color = c)
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Txt(r.str("title"), weight = FontWeight.SemiBold, lines = 2, translate = false)
                Muted("${r.str("course")} · ${r.int("correct")}/${r.int("total")} töğri · ${dateText(r.str("date"))}", lines = 2, translate = false)
            }
            Spacer(Modifier.width(8.dp))
            if (r.bool("passed")) Icon(Icons.Rounded.TaskAlt, "Ötdi", Modifier.size(24.dp), p.green)
            else Icon(Icons.Rounded.HighlightOff, "Ötmadi", Modifier.size(24.dp), p.red)
        }
    }
}
