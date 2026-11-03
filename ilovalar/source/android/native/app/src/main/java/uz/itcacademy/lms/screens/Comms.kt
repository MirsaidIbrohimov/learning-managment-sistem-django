package uz.itcacademy.lms.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import uz.itcacademy.lms.*
import uz.itcacademy.lms.ui.*

private const val CHAT_POLL_MS = 5000L
private const val CHAT_MAX_BYTES = 1024 * 1024

// ───────── Vazifalarim ─────────
@Composable
fun MyHomeworkScreen() {
    val load = rememberLoad(Unit) { Api.rows(Api.get("/api/v1/app/homework/", fresh = true).optJSONArray("results")) }
    var filter by remember { mutableStateOf("") }
    Page(bottom = 40.dp) {
        BackHeader(t("Vazifalarim"), onBack = { AppState.back() })
        val data = load.data
        when {
            load.error != null -> ErrorState(load.error, load.retry)
            data == null -> SkeletonList(5)
            data.isEmpty() -> EmptyState(Icons.Rounded.Description, "Hali vazifa topşirmagansiz", "Vazifalar kurs darslari içida topşiriladi.")
            else -> {
                Chips(
                    listOf("" to "${t("Barçasi")} ${data.size}", "revision" to t("Qayta işlaş kerak"), "pending" to t("Tekşirilmoqda"), "graded" to t("Baholangan")),
                    filter,
                ) { filter = it }
                data.filter {
                    when (filter) {
                        "" -> true
                        "pending" -> it.str("status") == "pending" || it.str("status") == "reviewing"
                        "graded" -> it.str("status") == "graded" || it.str("status") == "accepted"
                        else -> it.str("status") == filter
                    }
                }.forEachIndexed { i, h ->
                    key(h.int("id")) {
                        Row(
                            Modifier.reveal(i).fillMaxWidth().press(scale = .98f) { AppState.open(Route.Lesson(h.int("lesson_id"))) }.card().padding(14.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            IcoBox(Icons.Rounded.Description, pal.blue)
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Txt(h.str("title"), weight = FontWeight.SemiBold, lines = 2, translate = false)
                                Muted("${h.str("course")} · ${dateText(h.str("submitted_at"))}", lines = 1, translate = false)
                                Row(Modifier.padding(top = 5.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                                    when (h.str("status")) {
                                        "graded", "accepted" -> TagGreen(h.str("status_display"))
                                        "revision" -> TagRed(h.str("status_display"))
                                        else -> TagAmber(h.str("status_display"))
                                    }
                                    if (h.int("unread") > 0) TagAccent("${h.int("unread")} ${t("yangi xabar")}", Icons.Rounded.ChatBubble)
                                }
                            }
                            if (!h.isNull("grade")) {
                                Spacer(Modifier.width(8.dp))
                                Txt("${h.int("grade")}", size = 20.sp, weight = FontWeight.Bold, color = pal.green, translate = false)
                            }
                        }
                    }
                }
            }
        }
    }
}

// ───────── Dars jadvali ─────────
@Composable
fun ScheduleScreen() {
    val load = rememberLoad(Unit) { Api.get("/api/v1/app/schedule/", fresh = true) }
    Page(bottom = 40.dp) {
        BackHeader(t("Dars jadvalim"), onBack = { AppState.back() })
        val d = load.data
        when {
            load.error != null -> ErrorState(load.error, load.retry)
            d == null -> SkeletonList(5)
            else -> {
                val days = Api.rows(d.optJSONArray("days"))
                val today = Api.rows(d.optJSONArray("today"))
                val next = d.optJSONObject("next")
                if (days.all { it.optJSONArray("lessons")?.length() == 0 }) {
                    EmptyState(Icons.Rounded.CalendarMonth, "Jadval hali yöq", "Guruhga qöşilganingizdan keyin dars kunlari şu yerda çiqadi.")
                    return@Page
                }
                if (next != null) Column(Modifier.reveal(0).fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(tint(next.str("course"))).padding(18.dp)) {
                    Txt("Keyingi dars", color = Color.White.copy(alpha = .8f), size = 12.5.sp)
                    Txt(next.str("course"), color = Color.White, size = 20.sp, weight = FontWeight.Bold, translate = false, modifier = Modifier.padding(top = 2.dp))
                    Txt("${next.str("start")} – ${next.str("end")}", color = Color.White, weight = FontWeight.SemiBold, translate = false, modifier = Modifier.padding(top = 4.dp))
                    Txt(listOf(next.str("name"), next.str("room")).filter { it.isNotEmpty() }.joinToString(" · "), color = Color.White.copy(alpha = .8f), size = 12.5.sp, translate = false)
                }
                if (today.isEmpty()) Muted("Bugun dars yöq", size = 13.5.sp)
                days.forEachIndexed { i, day ->
                    val lessons = Api.rows(day.optJSONArray("lessons"))
                    Column(
                        Modifier.reveal(i + 1).fillMaxWidth().card(fill = if (day.bool("is_today")) pal.a1.copy(alpha = .12f) else pal.surface).padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Txt(day.str("name"), Modifier.weight(1f), weight = FontWeight.SemiBold)
                            if (day.bool("is_today")) TagAccent("Bugun")
                        }
                        if (lessons.isEmpty()) Muted("Dars yöq")
                        lessons.forEach { l ->
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.width(56.dp)) {
                                    Txt(l.str("start"), weight = FontWeight.Bold, size = 13.5.sp, translate = false)
                                    Muted(l.str("end"), size = 11.5.sp, translate = false)
                                }
                                Spacer(Modifier.width(8.dp))
                                Column(Modifier.weight(1f)) {
                                    Txt(l.str("course"), weight = FontWeight.Medium, lines = 1, translate = false)
                                    Muted(listOf(l.str("name"), l.strOrNull("teacher").orEmpty(), l.str("room")).filter { it.isNotEmpty() }.joinToString(" · "), lines = 2, translate = false)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

// ───────── Xabarlar ─────────
@Composable
fun MessagesScreen() {
    val load = rememberLoad(Unit) { Api.rows(Api.get("/api/v1/app/messages/", fresh = true).optJSONArray("results")) }
    val readNow = remember { mutableStateListOf<Int>() }
    val scope = rememberCoroutineScope()
    Page(bottom = 40.dp) {
        BackHeader(t("Xabarlar"), onBack = { AppState.back() })
        val data = load.data
        when {
            load.error != null -> ErrorState(load.error, load.retry)
            data == null -> SkeletonList(6)
            data.isEmpty() -> EmptyState(Icons.Rounded.Mail, "Xabarlar yöq", "Yangi bildirişnomalar şu yerda çiqadi.")
            else -> data.forEachIndexed { i, m ->
                key(m.int("id")) {
                    val unread = m.bool("personal") && !m.bool("is_read") && m.int("id") !in readNow
                    Row(
                        Modifier.reveal(i).fillMaxWidth().press(scale = .985f) {
                            if (unread) {
                                readNow += m.int("id")
                                scope.launch { runCatching { Api.post("/api/v1/app/messages/${m.int("id")}/read/") } }
                            }
                            Sheets.show { close ->
                                Txt(m.str("title"), size = 18.sp, weight = FontWeight.Bold, translate = false)
                                Muted(listOfNotNull(m.strOrNull("sender"), dateText(m.str("created_at"))).joinToString(" · "), Modifier.padding(top = 4.dp, bottom = 12.dp), translate = false)
                                Txt(stripHtml(m.str("content")), translate = false, color = pal.text2)
                                Spacer(Modifier.height(16.dp))
                                Btn("Yopiş", Modifier.fillMaxWidth(), onClick = close)
                            }
                        }.card().padding(14.dp),
                    ) {
                        Box {
                            IcoBox(Icons.Rounded.Mail, if (unread) pal.a1 else pal.muted)
                            if (unread) Box(Modifier.align(Alignment.TopEnd).size(9.dp).clip(CircleShape).background(pal.red))
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Txt(m.str("title"), weight = if (unread) FontWeight.Bold else FontWeight.Medium, lines = 2, translate = false)
                            Muted(stripHtml(m.str("content")), lines = 2, translate = false)
                            Muted(ago(m.str("created_at")), Modifier.padding(top = 3.dp), 11.5.sp, translate = false)
                        }
                    }
                }
            }
        }
    }
}

// ───────── Suhbatlar ─────────
@Composable
fun ChatsScreen() {
    var q by remember { mutableStateOf("") }
    val load = rememberLoad(Unit) { Api.rows(Api.get("/api/v1/app/chat/sidebar/", fresh = true).optJSONArray("items")) }
    val search = rememberLoad(q) {
        val term = q.trim()
        if (term.length < 2) emptyList()
        else {
            delay(350)
            Api.rows(Api.get("/api/v1/app/chat/users/search/", mapOf("q" to term), fresh = true).optJSONArray("users"))
        }
    }
    Page(bottom = 40.dp) {
        BackHeader(t("Suhbatlar"), onBack = { AppState.back() })
        Field(q, { q = it }, "Ism yoki login böyiça qidiriş", icon = Icons.Rounded.Search)
        val data = load.data
        if (q.trim().length >= 2) {
            val users = search.data.orEmpty()
            if (!search.loading && users.isEmpty()) EmptyState(Icons.Rounded.Search, "Hech narsa topilmadi")
            users.forEach { u ->
                key(u.int("id")) {
                    Row2(
                        u.str("name"), u.str("sub"), translate = false,
                        leading = { Avatar(u.strOrNull("photo"), u.str("name")) },
                    ) { AppState.open(Route.ChatThread("dm", u.int("id"), u.str("name"))) }
                }
            }
            return@Page
        }
        when {
            load.error != null -> ErrorState(load.error, load.retry)
            data == null -> SkeletonList(6)
            data.isEmpty() -> EmptyState(Icons.Rounded.ChatBubble, "Hali suhbat yöq", "Qidiruvdan öqituvçi yoki kursdoşingizni toping.")
            else -> data.forEachIndexed { i, it ->
                key(it.str("kind"), it.int("id")) {
                    Row(
                        Modifier.reveal(i).fillMaxWidth().press(scale = .985f) { AppState.open(Route.ChatThread(it.str("kind"), it.int("id"), it.str("name"))) }.card().padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Box {
                            Avatar(it.strOrNull("photo"), it.str("name"), 46.dp)
                            if (it.bool("is_online")) Box(Modifier.align(Alignment.BottomEnd).size(12.dp).clip(CircleShape).background(pal.green))
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                if (it.str("kind") == "group") { Icon(Icons.Rounded.Groups, null, Modifier.size(15.dp), pal.muted); Spacer(Modifier.width(4.dp)) }
                                Txt(it.str("name"), Modifier.weight(1f), weight = FontWeight.SemiBold, lines = 1, translate = false)
                                Muted(it.str("last_at"), size = 11.5.sp, translate = false)
                            }
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Muted(stripHtml(it.str("last_message")), Modifier.weight(1f), lines = 1, translate = false)
                                if (it.int("unread") > 0) Box(Modifier.clip(CircleShape).background(pal.a1).padding(horizontal = 7.dp, vertical = 2.dp)) {
                                    Txt("${it.int("unread")}", size = 11.sp, weight = FontWeight.Bold, color = Color.White, translate = false)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun Bubble(text: String, time: String, mine: Boolean, sender: String?, fileUrl: String? = null, fileName: String? = null) {
    val ctx = LocalContext.current
    val p = pal
    Box(Modifier.fillMaxWidth(), contentAlignment = if (mine) Alignment.CenterEnd else Alignment.CenterStart) {
        Column(
            Modifier.widthIn(max = 310.dp).clip(RoundedCornerShape(18.dp, 18.dp, if (mine) 5.dp else 18.dp, if (mine) 18.dp else 5.dp))
                .background(if (mine) p.a1 else p.surface2).padding(horizontal = 12.dp, vertical = 8.dp),
        ) {
            if (sender != null) Txt(sender, size = 12.sp, weight = FontWeight.SemiBold, color = p.a1, lines = 1, translate = false)
            if (fileUrl != null) Row(
                Modifier.padding(vertical = 3.dp).press { openBrowser(ctx, Api.media(fileUrl) ?: fileUrl) },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Rounded.AttachFile, null, Modifier.size(16.dp), if (mine) Color.White else p.a1)
                Spacer(Modifier.width(4.dp))
                Txt(fileName ?: t("Fayl"), size = 13.sp, color = if (mine) Color.White else p.a1, lines = 1, translate = false)
            }
            if (text.isNotEmpty()) Txt(text, color = if (mine) Color.White else p.text, translate = false)
            Txt(time, Modifier.align(Alignment.End).padding(top = 2.dp), 10.5.sp, color = if (mine) Color.White.copy(alpha = .75f) else p.muted, translate = false)
        }
    }
}

@Composable
fun ChatThreadScreen(kind: String, id: Int, name: String) {
    val scope = rememberCoroutineScope()
    val base = if (kind == "group") "/api/v1/app/chat/group/$id" else "/api/v1/app/chat/direct/$id"
    val messages = remember { mutableStateListOf<JSONObject>() }
    var loaded by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<ApiError?>(null) }
    var partnerSub by remember { mutableStateOf<String?>(null) }
    var text by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var attachment by remember { mutableStateOf<PickedFile?>(null) }
    var attempt by remember { mutableIntStateOf(0) }
    val list = rememberLazyListState()
    val pick = rememberFilePicker(CHAT_MAX_BYTES) { attachment = it }

    fun merge(rows: List<JSONObject>) {
        val known = messages.map { it.int("id") }.toHashSet()
        rows.filter { it.int("id") !in known }.forEach { messages += it }
    }

    LaunchedEffect(attempt) {
        error = null
        while (true) {
            try {
                val after = messages.lastOrNull()?.int("id")
                val r = Api.get("$base/messages/", mapOf("after" to after), fresh = true)
                merge(Api.rows(r.optJSONArray("messages")))
                r.optJSONObject("partner")?.let { partnerSub = it.strOrNull("sub") }
                loaded = true
                error = null
            } catch (e: ApiError) {
                if (!loaded) { error = e; return@LaunchedEffect }
            }
            delay(CHAT_POLL_MS)
        }
    }
    LaunchedEffect(messages.size) { if (messages.isNotEmpty()) list.animateScrollToItem(messages.lastIndex) }

    fun send() {
        val body = text.trim()
        val file = attachment
        if (body.isEmpty() && file == null) return
        sending = true
        scope.launch {
            try {
                val r = Api.upload("$base/send/", mapOf("message" to body), if (file != null) "file" else null, file)
                r.optJSONObject("message")?.let { merge(listOf(it)) }
                text = ""
                attachment = null
            } catch (e: ApiError) {
                Toasts.show(e.message ?: "", "err")
            }
            sending = false
        }
    }

    Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding()) {
        Box(Modifier.padding(start = 16.dp, end = 16.dp, top = 10.dp, bottom = 8.dp)) {
            BackHeader(name, partnerSub, onBack = { AppState.back() })
        }
        val err = error
        when {
            err != null -> Box(Modifier.weight(1f)) { ErrorState(err) { attempt++ } }
            !loaded -> Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) { Spinner(28.dp) }
            messages.isEmpty() -> Box(Modifier.weight(1f)) { EmptyState(Icons.Rounded.ChatBubble, "Hali xabar yöq", "Birinçi xabarni yozing.") }
            else -> LazyColumn(
                Modifier.weight(1f).fillMaxWidth(), list,
                contentPadding = PaddingValues(horizontal = 14.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                items(messages, key = { it.int("id") }) { m ->
                    Bubble(
                        stripHtml(m.str("message")), m.str("created_at").substringAfter(' ', m.str("created_at")), m.bool("is_me"),
                        if (kind == "group" && !m.bool("is_me")) m.optJSONObject("sender")?.str("name") else null,
                        m.strOrNull("file_url"), m.strOrNull("file_name"),
                    )
                }
            }
        }
        attachment?.let { f ->
            Row(Modifier.padding(horizontal = 14.dp, vertical = 4.dp).fillMaxWidth().card().padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.AttachFile, null, Modifier.size(16.dp), pal.a1); Spacer(Modifier.width(6.dp))
                Txt(f.name, Modifier.weight(1f), 13.sp, lines = 1, translate = false)
                Icon(Icons.Rounded.Close, t("Olib taşlaş"), Modifier.size(18.dp).press { attachment = null }, pal.muted)
            }
        }
        if (err == null) Row(Modifier.padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Tinted(pal.surface2, Modifier.size(42.dp).press { pick("*/*") }, CircleShape) { Icon(Icons.Rounded.AttachFile, t("Fayl biriktiriş"), Modifier.size(20.dp), pal.text2) }
            Spacer(Modifier.width(8.dp))
            Field(text, { text = it }, "Xabar yozing…", Modifier.weight(1f), single = false, minHeight = 42.dp)
            Spacer(Modifier.width(8.dp))
            val ready = (text.isNotBlank() || attachment != null) && !sending
            Tinted(if (ready) pal.a1 else pal.surface2, Modifier.size(42.dp).press(enabled = ready) { send() }, CircleShape) {
                if (sending) Spinner(18.dp, Color.White) else Icon(Icons.Rounded.Send, t("Yuboriş"), Modifier.size(19.dp), if (ready) Color.White else pal.muted)
            }
        }
    }
}
