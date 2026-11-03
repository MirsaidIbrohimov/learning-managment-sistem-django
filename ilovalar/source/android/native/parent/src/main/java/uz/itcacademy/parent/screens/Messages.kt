package uz.itcacademy.parent.screens

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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import org.json.JSONObject
import uz.itcacademy.parent.*
import uz.itcacademy.parent.ui.*

/** Öquv markazi bilan yozishma: tanlangan farzand bo'yicha bitta chat. */
@Composable
fun MessagesScreen() {
    val p = pal
    val scope = rememberCoroutineScope()
    val childId = AppState.child?.int("id") ?: 0
    val load = key(childId) { rememberLoad { Api.get("messages/", mapOf("child" to childId), fresh = true) } }
    var text by remember { mutableStateOf("") }
    var topic by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    val list = rememberLazyListState()
    val events = load.data?.list("events").orEmpty()
    LaunchedEffect(events.size) {
        if (events.isNotEmpty()) list.animateScrollToItem(events.size - 1)
        if (load.data != null) runCatching { AppState.refresh() }   // o'qilmaganlar soni yangilansin
    }

    Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding()) {
        Column(Modifier.padding(start = 16.dp, end = 16.dp, top = 10.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            BackHeader("Xabarlar", "Öquv markazi bilan yozişma", onBack = { AppState.back() })
            if (AppState.children.size > 1) ChildSwitcher()
        }
        Box(Modifier.weight(1f).fillMaxWidth()) {
            val d = load.data
            when {
                AppState.children.isEmpty() -> NoChild()
                d == null && load.error != null -> ErrorState(load.error, load.retry)
                d == null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Spinner() }
                events.isEmpty() -> EmptyState(Icons.Rounded.Forum, "Hali xabar yöq",
                    "Farzandingiz öqişi, davomati yoki tölov böyiça savolingizni yozing — öquv markazi javob beradi.")
                else -> LazyColumn(state = list, contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    var prevDay = ""
                    val rows = events.map { e -> val day = dayLabel(e.str("at")); val sep = day != prevDay; prevDay = day; Triple(e, day, sep) }
                    items(rows) { (e, day, sep) ->
                        Column {
                            if (sep) Box(Modifier.fillMaxWidth().padding(vertical = 6.dp), contentAlignment = Alignment.Center) {
                                Tag(day)
                            }
                            Bubble(e)
                        }
                    }
                    if (d.bool("waiting")) item {
                        Row(Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Rounded.Schedule, null, Modifier.size(14.dp), p.muted)
                            Spacer(Modifier.width(5.dp))
                            Muted("Javob kutilmoqda", size = 12.sp)
                        }
                    }
                }
            }
        }
        if (AppState.children.isNotEmpty()) Column(Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
            val topics = load.data?.strings("topics").orEmpty()
            if (topics.isNotEmpty()) Chips(topics.map { it to it }, topic, Modifier.padding(bottom = 8.dp)) { topic = if (topic == it) "" else it }
            Row(verticalAlignment = Alignment.Bottom) {
                Field(text, { text = it.take(4000) }, "Xabar yozing…", Modifier.weight(1f), single = false, minHeight = 48.dp)
                Spacer(Modifier.width(8.dp))
                Box(
                    Modifier.size(48.dp).clip(CircleShape).background(Brush.linearGradient(listOf(p.a1, p.a2)))
                        .press(text.isNotBlank() && !busy) {
                            busy = true
                            scope.launch {
                                try {
                                    Api.post("messages/", JSONObject().put("child_id", childId).put("topic", topic).put("message", text.trim()))
                                    text = ""; topic = ""
                                    load.retry()
                                } catch (e: ApiError) { Toasts.show(e.message.orEmpty(), "err") }
                                busy = false
                            }
                        },
                    contentAlignment = Alignment.Center,
                ) { if (busy) Spinner(20.dp, Color.White) else Icon(Icons.Rounded.Send, "Yuboriş", Modifier.size(22.dp), Color.White) }
            }
        }
    }
}

@Composable
private fun Bubble(e: JSONObject) {
    val p = pal
    when (e.str("kind")) {
        "notice" -> Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(p.blue.copy(alpha = .12f)).padding(12.dp),
            verticalAlignment = Alignment.Top,
        ) {
            Icon(Icons.Rounded.Campaign, null, Modifier.size(20.dp), p.blue)
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Txt(e.str("title"), weight = FontWeight.SemiBold, translate = false)
                Txt(e.str("text"), size = 13.5.sp, color = p.text2, translate = false)
                Muted(timeText(e.str("at")), size = 11.sp)
            }
        }
        "me" -> Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            Column(
                Modifier.widthIn(max = 290.dp).clip(RoundedCornerShape(20.dp, 20.dp, 6.dp, 20.dp))
                    .background(Brush.linearGradient(listOf(p.a1, p.a2))).padding(horizontal = 14.dp, vertical = 10.dp),
            ) {
                if (e.str("title").isNotEmpty()) Txt(e.str("title"), size = 11.5.sp, weight = FontWeight.SemiBold, color = Color.White.copy(alpha = .8f), translate = false)
                Txt(e.str("text"), color = Color.White, translate = false)
                Row(Modifier.align(Alignment.End), verticalAlignment = Alignment.CenterVertically) {
                    Txt(timeText(e.str("at")), size = 10.5.sp, color = Color.White.copy(alpha = .75f))
                    Spacer(Modifier.width(4.dp))
                    Icon(if (e.bool("answered")) Icons.Rounded.DoneAll else Icons.Rounded.Done, null, Modifier.size(14.dp), Color.White.copy(alpha = .85f))
                }
            }
        }
        else -> Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Start) {
            Column(
                Modifier.widthIn(max = 290.dp).clip(RoundedCornerShape(20.dp, 20.dp, 20.dp, 6.dp)).background(p.surface2)
                    .padding(horizontal = 14.dp, vertical = 10.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Txt(e.str("by"), size = 11.5.sp, weight = FontWeight.SemiBold, color = p.a1, translate = false)
                    if (e.bool("new")) { Spacer(Modifier.width(6.dp)); TagAccent("Yangi") }
                }
                Txt(e.str("text"), translate = false)
                Muted(timeText(e.str("at")), Modifier.align(Alignment.End), 10.5.sp)
            }
        }
    }
}

// ───────── Bildirishnomalar ─────────
@Composable
fun NotificationsScreen() {
    val p = pal
    val ctx = LocalContext.current
    val since = remember { isoUtc(System.currentTimeMillis() - 13L * 86_400_000L) }
    val load = rememberLoad { Api.get("notifications/", mapOf("since" to since), fresh = true) }
    val viewedBefore = remember { ctx.getSharedPreferences("itcp_notify", android.content.Context.MODE_PRIVATE).getLong("viewedAt", 0L) }
    LaunchedEffect(load.data) { if (load.data != null) AppState.markNotifViewed(ctx) }
    Refreshable({ load.retry() }) {
        Page {
            BackHeader("Bildirişnomalar", "Oxirgi 2 hafta", onBack = { AppState.back() })
            val d = load.data
            when {
                d == null && load.error != null -> ErrorState(load.error, load.retry)
                d == null -> SkeletonList(6, 70.dp)
                d.list("events").isEmpty() -> EmptyState(Icons.Rounded.NotificationsNone, "Bildirişnoma yöq",
                    "Farzandingiz test topşirsa, baholansa yoki darsga kelmasa — şu yerda va telefoningizda xabar paydo böladi.")
                else -> {
                    var prev = ""
                    d.list("events").forEachIndexed { i, e ->
                        val day = dayLabel(e.str("at"))
                        if (day != prev) { Muted(day.uppercase(), Modifier.padding(top = 6.dp), 11.5.sp); prev = day }
                        val (ic, c) = kindStyle(e.str("kind"))
                        val unseen = (parseDate(e.str("at"))?.time ?: 0L) > viewedBefore
                        Row(
                            Modifier.reveal(i).fillMaxWidth().card(RoundedCornerShape(18.dp))
                                .press { AppState.go(e.strOrNull("target"), e.int("child_id")) }.padding(14.dp),
                            verticalAlignment = Alignment.Top,
                        ) {
                            IcoBox(ic, c, 40.dp)
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Txt(e.str("title"), Modifier.weight(1f), weight = FontWeight.SemiBold, lines = 2, translate = false)
                                    if (unseen) Dot(p.a1)
                                }
                                Txt(e.str("text"), size = 13.5.sp, color = p.text2, lines = 3, translate = false)
                                Muted("${e.str("child")} · ${timeText(e.str("at"))}", size = 11.5.sp, translate = false)
                            }
                        }
                    }
                }
            }
        }
    }
}

