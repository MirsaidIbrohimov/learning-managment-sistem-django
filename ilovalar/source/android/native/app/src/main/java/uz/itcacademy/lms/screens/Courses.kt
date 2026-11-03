package uz.itcacademy.lms.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import org.json.JSONObject
import uz.itcacademy.lms.*
import uz.itcacademy.lms.ui.*

@Composable
fun CourseThumb(p: JSONObject, size: Dp) {
    Box(Modifier.size(size).clip(RoundedCornerShape(size * .28f)).background(tint(p.str("name"))), contentAlignment = Alignment.Center) {
        Txt(initials(p.str("name")), color = Color.White, weight = FontWeight.Bold, translate = false)
        Api.media(p.strOrNull("photo"))?.let { AsyncImage(it, null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
    }
}

@Composable
private fun CourseCard(p: JSONObject, enrolledAt: String?, index: Int) {
    Column(Modifier.reveal(index).fillMaxWidth().press(scale = .98f) { AppState.open(Route.Course(p.int("id"))) }.card()) {
        Box(Modifier.fillMaxWidth().height(150.dp).background(tint(p.str("name"))), contentAlignment = Alignment.Center) {
            Txt(initials(p.str("name")), size = 38.sp, weight = FontWeight.ExtraBold, color = Color.White.copy(alpha = .85f), translate = false)
            Api.media(p.strOrNull("photo"))?.let { AsyncImage(it, p.str("name"), Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
            Row(Modifier.align(Alignment.TopStart).padding(10.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (p.bool("is_mandatory")) Tag("Majburiy", Color.White, Color(0x99101020), Icons.Rounded.Star)
                Tag(if (p.bool("is_paid")) "Pullik" else "Bepul", Color.White, Color(0x99101020))
            }
        }
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Txt(p.str("name"), size = 15.sp, weight = FontWeight.SemiBold, lines = 2, translate = false)
            stripHtml(p.strOrNull("description")).takeIf { it.isNotEmpty() }?.let { Muted(it, lines = 2, translate = false) }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                Muted("${num(p.int("student_count"))} ${t("öquvçi")}", translate = false)
                if (enrolledAt != null) Muted(dateText(enrolledAt), translate = false)
            }
        }
    }
}

@Composable
fun CoursesScreen() {
    var tab by rememberSaveableInt()
    var q by remember { mutableStateOf("") }
    val load = rememberLoad(tab) {
        if (tab == 0) Api.getAll("/api/v1/my/enrollments/").map { (it.optJSONObject("profession") ?: JSONObject()) to it.strOrNull("enrolled_at") }
        else Api.getAll("/api/v1/courses/").map { it to null }
    }
    Page {
        H1("Kurslar", "Kursni tanlang — bölimlar va darslar röyxati oçiladi", Modifier.reveal(0))
        Segmented(listOf("Mening kurslarim", "Barça kurslar"), tab, Modifier.reveal(1)) { tab = it }
        Field(q, { q = it }, "Kurs nomi böyiça qidiriş", Modifier.reveal(2), Icons.Rounded.Search)
        val data = load.data
        when {
            load.error != null -> ErrorState(load.error, load.retry)
            data == null || load.loading -> SkeletonList(3, 210.dp)
            else -> {
                val shown = data.filter { it.first.str("name").contains(q.trim(), true) }
                if (shown.isEmpty()) {
                    if (data.isNotEmpty()) EmptyState(Icons.Rounded.Search, "Hech narsa topilmadi", "Boşqa söz bilan qidirib köring.")
                    else if (tab == 0) EmptyState(Icons.Rounded.PlayCircle, "Hali kursga yozilmagansiz", "Barça kurslar böliminda mavjud kurslarni körishingiz mumkin.") {
                        Btn("Barça kurslar", kind = BtnKind.Primary, icon = Icons.Rounded.GridView) { tab = 1 }
                    } else EmptyState(Icons.Rounded.PlayCircle, "Kurslar topilmadi")
                }
                shown.forEachIndexed { i, (p, at) -> key(p.int("id")) { CourseCard(p, at, i) } }
            }
        }
    }
}

@Composable private fun rememberSaveableInt() = androidx.compose.runtime.saveable.rememberSaveable { mutableIntStateOf(0) }

private class CourseData(val p: JSONObject, val groups: List<Group>, val lessons: List<JSONObject>, val state: JSONObject)
private class Group(val title: String, val lessons: List<JSONObject>)

fun openLessonById(r: JSONObject) = AppState.open(Route.Lesson(r.int("id")))

private fun lessonStatus(l: JSONObject): Pair<String, String>? = when {
    l.bool("completed") -> null
    l.str("status") == "revision" -> "Qayta işlaş kerak" to "red"
    l.str("status") == "pending" || l.str("status") == "reviewing" -> "Tekşirilmoqda" to "amber"
    l.bool("attempted") && l.has("passed") && !l.bool("passed") -> "Ötilmagan" to "red"
    else -> null
}

@Composable
fun CourseScreen(id: Int) {
    val load = rememberLoad(id) {
        val p = Api.get("/api/v1/courses/$id/")
        val state = Api.get("/api/v1/app/courses/$id/lessons/", fresh = true)
        val rows = Api.rows(state.optJSONArray("lessons"))
        val sections = Api.rows(state.optJSONArray("sections"))
        val bySec = sections.associate { it.int("id") to mutableListOf<JSONObject>() }
        val loose = mutableListOf<JSONObject>()
        rows.forEach { l -> (if (l.isNull("section")) null else bySec[l.int("section")])?.add(l) ?: loose.add(l) }
        val groups = sections.filter { bySec[it.int("id")].orEmpty().isNotEmpty() }.map { Group(it.str("title"), bySec.getValue(it.int("id"))) }.toMutableList()
        if (loose.isNotEmpty()) groups += Group(if (groups.isEmpty()) "Darslar" else "Boşqa darslar", loose)
        CourseData(p, groups, rows, state)
    }
    var type by remember { mutableStateOf("") }
    var q by remember { mutableStateOf("") }
    val open = remember { mutableStateMapOf<Int, Boolean>() }
    val d = load.data

    Page(bottom = 40.dp) {
        BackHeader(d?.p?.str("name") ?: t("Kurslar"), onBack = { AppState.back() })
        when {
            load.error != null -> ErrorState(load.error, load.retry)
            d == null -> { Shimmer(Modifier.fillMaxWidth().height(210.dp)); SkeletonList(6) }
            else -> {
                val ordered = d.groups.flatMap { it.lessons }
                val enrolled = d.state.bool("enrolled")
                // Tekshiruvdagi ish uchun o'quvchi hozir hech narsa qila olmaydi: keyingisiga o'tamiz
                val next = ordered.firstOrNull {
                    !it.bool("completed") && it.str("lesson_type") != "dictionary" && it.isNull("locked") &&
                        it.str("status") != "pending" && it.str("status") != "reviewing"
                }
                val course = d.p
                fun launch(l: JSONObject) {
                    if (!l.isNull("locked")) Toasts.show(l.str("locked_message"), "info")
                    else AppState.open(Route.Lesson(l.int("id")))
                }
                Box(Modifier.reveal(0).fillMaxWidth().clip(RoundedCornerShape(26.dp)).background(tint(course.str("name")))) {
                    Api.media(course.strOrNull("photo"))?.let { AsyncImage(it, null, Modifier.matchParentSize(), contentScale = ContentScale.Crop) }
                    Box(Modifier.matchParentSize().background(Brush.verticalGradient(listOf(Color(0x40080614), Color(0xE6080614)))))
                    Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Tag(if (course.bool("is_paid")) "Pullik" else "Bepul", Color.White, Color(0x29FFFFFF))
                            if (course.bool("is_mandatory")) Tag("Majburiy", Color.White, Color(0x29FFFFFF), Icons.Rounded.Star)
                        }
                        Txt(course.str("name"), size = 24.sp, weight = FontWeight.Bold, color = Color.White, translate = false)
                        stripHtml(course.strOrNull("description")).takeIf { it.isNotEmpty() }?.let { Txt(it, color = Color.White.copy(alpha = .82f), lines = 3, size = 13.5.sp, translate = false) }
                        Txt("${num(d.groups.size)} ${t("bölim")} · ${num(d.lessons.size)} ${t("dars")} · ${num(course.int("student_count"))} ${t("öquvçi")}", color = Color.White.copy(alpha = .86f), size = 12.5.sp, translate = false)
                        if (!enrolled) {
                            Spacer(Modifier.height(4.dp))
                            OpenSiteButton("Kursga yoziliş", "/professions/$id/")
                        } else if (d.lessons.isNotEmpty()) {
                            val done = d.state.int("done")
                            val total = d.state.int("total")
                            Column(Modifier.padding(top = 6.dp).fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Color(0x29FFFFFF)).padding(14.dp)) {
                                Row {
                                    Txt("Bajarilgan darslar", Modifier.weight(1f), 12.5.sp, color = Color.White)
                                    Txt("${num(done)} / ${num(total)}", size = 12.5.sp, weight = FontWeight.Bold, color = Color.White, translate = false)
                                }
                                Spacer(Modifier.height(8.dp))
                                ProgressBar(if (total > 0) done.toFloat() / total else 0f, color = Color.White, track = Color(0x33FFFFFF))
                                if (next != null) {
                                    Spacer(Modifier.height(12.dp))
                                    Btn(if (done == 0) "Birinçi darsni boşlaş" else "Davom ettiriş", Modifier.fillMaxWidth(), BtnKind.Primary, Icons.Rounded.PlayArrow) { launch(next) }
                                    Txt(next.str("title"), Modifier.padding(top = 6.dp).align(Alignment.CenterHorizontally), 11.5.sp, color = Color.White.copy(alpha = .75f), lines = 1, translate = false)
                                } else ordered.firstOrNull { !it.isNull("locked") }?.let { waiting ->
                                    // Davom etish tugmasi nega yo'qligini o'quvchi bilib tursin
                                    Row(Modifier.padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                                        Icon(Icons.Rounded.Lock, null, Modifier.size(16.dp), Color.White)
                                        Spacer(Modifier.width(8.dp))
                                        Txt(waiting.str("locked_message"), size = 12.5.sp, color = Color.White, translate = false)
                                    }
                                }
                            }
                        }
                    }
                }
                if (d.state.bool("blocked")) Row(Modifier.fillMaxWidth().card(fill = pal.red.copy(alpha = .13f)).padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Rounded.Lock, null, Modifier.size(20.dp), pal.red); Spacer(Modifier.width(10.dp))
                    Column {
                        Txt("Kurs vaqtinça bloklangan", weight = FontWeight.SemiBold)
                        d.state.strOrNull("blocked_reason")?.let { Muted(it, translate = false) }
                    }
                }
                if (d.state.optJSONObject("certificate") != null) Row(Modifier.fillMaxWidth().press { AppState.open(Route.Results) }.card(fill = pal.green.copy(alpha = .13f)).padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Rounded.WorkspacePremium, null, Modifier.size(22.dp), pal.green); Spacer(Modifier.width(10.dp))
                    Txt("Kurs sertifikati berilgan", Modifier.weight(1f), weight = FontWeight.SemiBold)
                    Icon(Icons.Rounded.ChevronRight, null, Modifier.size(20.dp), pal.muted)
                }

                val counts = d.lessons.groupingBy { it.str("lesson_type") }.eachCount()
                Chips(
                    listOf("" to "${t("Barçasi")} ${d.lessons.size}") + counts.map { (k, v) -> k to "${t(LESSON_TYPE[k] ?: k)} $v" },
                    type, Modifier.reveal(1),
                ) { type = it }
                Field(q, { q = it }, "Dars qidiriş", Modifier.reveal(2), Icons.Rounded.Search)

                val filtering = q.isNotBlank() || type.isNotEmpty()
                if (d.groups.isEmpty()) EmptyState(Icons.Rounded.PlayCircle, "Bu kursda hali darslar yöq")
                d.groups.forEachIndexed { i, g ->
                    val shown = g.lessons.filter { (type.isEmpty() || it.str("lesson_type") == type) && (q.isBlank() || it.str("title").contains(q.trim(), true)) }
                    if (shown.isEmpty()) return@forEachIndexed
                    val defaultOpen = next?.let { n -> n in g.lessons } ?: (i == 0)
                    val isOpen = open[i] ?: (defaultOpen || filtering)
                    val rot by animateFloatAsState(if (isOpen) 180f else 0f, label = "chev")
                    val groupLocked = g.lessons.all { !it.isNull("locked") }
                    Column(Modifier.reveal(i + 3).fillMaxWidth().card()) {
                        Row(
                            Modifier.fillMaxWidth().press(scale = .99f) { open[i] = !isOpen }.padding(14.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Tinted(pal.a1.copy(alpha = .16f), Modifier.size(34.dp), RoundedCornerShape(10.dp)) {
                                if (groupLocked) Icon(Icons.Rounded.Lock, t("Qulflangan"), Modifier.size(17.dp), pal.a1)
                                else Txt("${i + 1}", weight = FontWeight.Bold, color = pal.a1, translate = false)
                            }
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Txt(g.title, weight = FontWeight.SemiBold, lines = 2, translate = false)
                                val req = g.lessons.filter { it.str("lesson_type") != "dictionary" }
                                Muted("${num(req.count { it.bool("completed") })} / ${num(req.size)} ${t("dars bajarilgan")}", translate = false)
                            }
                            Icon(Icons.Rounded.ExpandMore, null, Modifier.size(22.dp).graphicsLayer { rotationZ = rot }, pal.muted)
                        }
                        AnimatedVisibility(isOpen) {
                            Column {
                                shown.forEachIndexed { j, l ->
                                    Hairline()
                                    val done = l.bool("completed")
                                    val locked = !l.isNull("locked")
                                    val isNext = next?.int("id") == l.int("id")
                                    val status = lessonStatus(l)
                                    Row(
                                        Modifier.fillMaxWidth().then(if (isNext) Modifier.background(pal.a1.copy(alpha = .08f)) else Modifier)
                                            .press(scale = .985f) { launch(l) }.padding(horizontal = 14.dp, vertical = 11.dp)
                                            .graphicsLayer { alpha = if (locked) .55f else 1f },
                                        verticalAlignment = Alignment.CenterVertically,
                                    ) {
                                        Tinted(if (done) pal.green.copy(alpha = .14f) else Color.Transparent, Modifier.size(24.dp), CircleShape) {
                                            if (done) Icon(Icons.Rounded.Check, t("Bajarilgan"), Modifier.size(14.dp), pal.green)
                                            else if (locked) Icon(Icons.Rounded.Lock, t("Qulflangan"), Modifier.size(14.dp), pal.muted)
                                            else Muted("${j + 1}", size = 12.sp, translate = false)
                                        }
                                        Spacer(Modifier.width(10.dp))
                                        IcoBox(lessonIcon(l.str("lesson_type")), lessonColor(l.str("lesson_type")), 32.dp)
                                        Spacer(Modifier.width(10.dp))
                                        Column(Modifier.weight(1f)) {
                                            Txt(l.str("title"), lines = 2, translate = false, color = if (done) pal.text2 else pal.text, weight = FontWeight.Medium)
                                            Muted(LESSON_TYPE[l.str("lesson_type")] ?: l.str("lesson_type"), size = 11.5.sp)
                                        }
                                        if (status != null) {
                                            Spacer(Modifier.width(6.dp))
                                            if (status.second == "red") TagRed(status.first) else TagAmber(status.first)
                                        } else if (isNext) { Spacer(Modifier.width(6.dp)); TagAccent("Keyingi", Icons.Rounded.PlayArrow) }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
