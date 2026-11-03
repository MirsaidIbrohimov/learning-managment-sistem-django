package uz.itcacademy.lms.screens

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.net.Uri
import android.os.Build
import android.os.SystemClock
import android.provider.OpenableColumns
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.Icon
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import uz.itcacademy.lms.*
import uz.itcacademy.lms.ui.*
import java.io.File

/** Ekran yopilganda ham tugashi kerak bo'lgan so'rovlar uchun. */
val AppScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

private const val HOMEWORK_MAX_BYTES = 5 * 1024 * 1024
private const val AUDIO_MAX_BYTES = 5 * 1024 * 1024

/** Tizim tanlagichidan kelgan faylni o'qiydi. Ruxsat kerak emas. */
suspend fun readPicked(ctx: Context, uri: Uri, maxBytes: Int): PickedFile = withContext(Dispatchers.IO) {
    var name = "fayl"
    var size = -1L
    ctx.contentResolver.query(uri, null, null, null, null)?.use { c ->
        if (c.moveToFirst()) {
            c.getColumnIndex(OpenableColumns.DISPLAY_NAME).takeIf { it >= 0 }?.let { c.getString(it)?.let { n -> name = n } }
            c.getColumnIndex(OpenableColumns.SIZE).takeIf { it >= 0 && !c.isNull(it) }?.let { size = c.getLong(it) }
        }
    }
    if (size > maxBytes) throw FileTooBig(maxBytes)
    val bytes = ctx.contentResolver.openInputStream(uri)?.use { input ->
        val out = java.io.ByteArrayOutputStream()
        val buf = ByteArray(16 * 1024)
        while (true) {
            val n = input.read(buf)
            if (n < 0) break
            out.write(buf, 0, n)
            if (out.size() > maxBytes) throw FileTooBig(maxBytes)
        }
        out.toByteArray()
    } ?: throw java.io.IOException("read")
    PickedFile(name, ctx.contentResolver.getType(uri), bytes)
}

class FileTooBig(val maxBytes: Int) : Exception()

/** Fayl tanlash: xatolar foydalanuvchiga xabar sifatida chiqadi. */
@Composable
fun rememberFilePicker(maxBytes: Int, onPicked: (PickedFile) -> Unit): (String) -> Unit {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            try {
                onPicked(readPicked(ctx, uri, maxBytes))
            } catch (e: FileTooBig) {
                Toasts.show("${t("Fayl juda katta. Eng köpi")} ${e.maxBytes / 1024 / 1024} MB", "err")
            } catch (e: java.io.IOException) {
                Toasts.show("Faylni öqib bölmadi", "err")
            }
        }
    }
    return { mime -> runCatching { launcher.launch(mime) }.onFailure { Toasts.show("Fayl tanlagiçi topilmadi", "err") } }
}

@Composable
fun LessonScreen(id: Int) {
    val load = rememberLoad(id) { Api.get("/api/v1/app/lessons/$id/", fresh = true) }
    val d = load.data
    LaunchedEffect(d) {
        if (d != null) {
            val course = d.optJSONObject("course") ?: JSONObject()
            Settings.markVisited(course.int("id"), id)
            Settings.pushRecent(id, d.str("title"), d.str("lesson_type"), course.int("id"), course.str("name"))
        }
    }
    val err = load.error
    when {
        err != null -> Page(bottom = 40.dp) {
            BackHeader(t("Dars"), onBack = { AppState.back() })
            val code = (err as? ApiError)?.code
            if (code in setOf("sequential", "daily", "final", "not_enrolled", "course_blocked")) {
                EmptyState(Icons.Rounded.Lock, "Bu dars hozirça yopiq", err.message.orEmpty()) {
                    Btn("Orqaga", icon = Icons.Rounded.ChevronLeft) { AppState.back() }
                }
            } else ErrorState(err, load.retry)
        }
        d == null -> Page(bottom = 40.dp) {
            BackHeader(t("Dars"), onBack = { AppState.back() })
            Shimmer(Modifier.fillMaxWidth().height(210.dp))
            SkeletonList(3)
        }
        else -> {
            val c = d.optJSONObject("content")
            when (d.str("lesson_type")) {
                "video" -> VideoLessonContent(d, c)
                "test" -> TestLessonContent(d, c, load.retry)
                else -> Page(bottom = 40.dp) {
                    BackHeader(d.str("title"), d.optJSONObject("course")?.str("name"), onBack = { AppState.back() })
                    when {
                        c == null -> EmptyState(Icons.Rounded.HourglassEmpty, "Bu dars hali tayyor emas")
                        d.str("lesson_type") == "homework" -> HomeworkContent(d, c, load.retry)
                        d.str("lesson_type") == "dictionary" -> DictionaryContent(c)
                        d.str("lesson_type") == "speaking" -> SpeakingContent(d, c, load.retry)
                    }
                    LessonNextButton(d, enabled = true)
                }
            }
        }
    }
}

@Composable
fun LessonNextButton(d: JSONObject, enabled: Boolean) {
    val next = d.optJSONObject("next") ?: return
    if (!enabled) return
    val locked = next.bool("locked")
    Row(
        Modifier.fillMaxWidth().press(scale = .98f) {
            if (locked) Toasts.show("Keyingi dars hali yopiq", "info") else AppState.replace(Route.Lesson(next.int("id")))
        }.card().padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IcoBox(lessonIcon(next.str("lesson_type")), lessonColor(next.str("lesson_type")))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Muted("Keyingi dars")
            Txt(next.str("title"), weight = FontWeight.SemiBold, lines = 2, translate = false)
        }
        Icon(if (locked) Icons.Rounded.Lock else Icons.Rounded.ChevronRight, null, Modifier.size(22.dp), pal.muted)
    }
}

// ───────── Lug'at ─────────
@Composable
private fun DictionaryContent(c: JSONObject) {
    var q by remember { mutableStateOf("") }
    val words = remember(c) { Api.rows(c.optJSONArray("words")) }
    c.strOrNull("description")?.let { Muted(it, size = 13.5.sp, translate = false) }
    Field(q, { q = it }, "Söz qidiriş", icon = Icons.Rounded.Search)
    val shown = words.filter { q.isBlank() || it.str("term").contains(q.trim(), true) || it.str("translation").contains(q.trim(), true) }
    Muted("${num(shown.size)} ${t("ta söz")}", translate = false)
    if (shown.isEmpty()) EmptyState(Icons.Rounded.Search, if (words.isEmpty()) "Luğatda hali söz yöq" else "Hech narsa topilmadi")
    shown.forEach { w ->
        key(w.int("id")) {
            Column(Modifier.fillMaxWidth().card().padding(14.dp)) {
                Txt(w.str("term"), size = 16.sp, weight = FontWeight.SemiBold, translate = false)
                Txt(w.str("translation"), color = pal.a1, weight = FontWeight.Medium, translate = false, modifier = Modifier.padding(top = 2.dp))
                w.strOrNull("example")?.let { Muted(it, Modifier.padding(top = 6.dp), translate = false) }
            }
        }
    }
}

// ───────── Uyga vazifa ─────────
@Composable
private fun HomeworkContent(d: JSONObject, c: JSONObject, reload: () -> Unit) {
    val lessonId = d.int("id")
    val hw = c.optJSONObject("homework") ?: JSONObject()
    val sub = c.optJSONObject("submission")
    val formats = hw.optJSONArray("allowed_formats")?.let { a -> (0 until a.length()).map { a.getString(it) } }.orEmpty()

    Column(Modifier.fillMaxWidth().card().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IcoBox(Icons.Rounded.Description, pal.blue); Spacer(Modifier.width(10.dp))
            Txt("Vazifa", Modifier.weight(1f), 15.sp, FontWeight.SemiBold)
            if (hw.bool("ai_check")) TagAccent("AI tekşiradi", Icons.Rounded.SmartToy)
        }
        Spacer(Modifier.height(10.dp))
        RichText(hw.str("description"))
        hw.strOrNull("due_date")?.let {
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.Schedule, null, Modifier.size(15.dp), if (hw.bool("is_deadline_passed")) pal.red else pal.muted)
                Spacer(Modifier.width(5.dp))
                Txt("${t("Muddat")}: $it", size = 12.5.sp, color = if (hw.bool("is_deadline_passed")) pal.red else pal.muted, translate = false)
            }
        }
        if (formats.isNotEmpty()) Muted("${t("Fayl turlari")}: ${formats.joinToString(" ")}", Modifier.padding(top = 4.dp), translate = false)
    }

    if (sub != null) SubmissionCard(sub)

    val status = sub?.str("status")
    val canEdit = sub?.bool("can_edit") == true
    var showResubmit by remember(sub) { mutableStateOf(false) }
    when {
        sub == null -> when {
            hw.bool("is_deadline_passed") && !hw.bool("allow_late") ->
                EmptyState(Icons.Rounded.EventBusy, "Topşiriş muddati tugagan", "Bu vazifani keç topşirişga ruxsat yöq.")
            else -> SubmitForm(lessonId, hw, "submit", "Vazifani yuboriş", null, reload)
        }
        canEdit -> SubmitForm(lessonId, hw, "edit", "Tahrirni saqlaş", sub, reload)
        status != "pending" && status != "reviewing" -> {
            val penalty = hw.int("resubmit_coin_penalty")
            if (!showResubmit) Btn("Qayta topşiriş", Modifier.fillMaxWidth(), if (status == "revision") BtnKind.Primary else BtnKind.Normal, Icons.Rounded.Refresh) { showResubmit = true }
            else {
                Row(Modifier.fillMaxWidth().card(fill = pal.amber.copy(alpha = .13f)).padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Rounded.WarningAmber, null, Modifier.size(20.dp), pal.amber); Spacer(Modifier.width(10.dp))
                    Txt("${t("Qayta topşirilganda jarima yeçiladi")}: $penalty coin", translate = false)
                }
                SubmitForm(lessonId, hw, "submit", "Qayta yuboriş", null, reload)
            }
        }
    }
    if (sub != null) HomeworkChat(lessonId)
}

@Composable
private fun SubmissionCard(sub: JSONObject) {
    val status = sub.str("status")
    val (color, icon) = when (status) {
        "graded", "accepted" -> pal.green to Icons.Rounded.CheckCircle
        "revision" -> pal.red to Icons.Rounded.Refresh
        else -> pal.amber to Icons.Rounded.HourglassTop
    }
    Column(Modifier.fillMaxWidth().card(fill = color.copy(alpha = .11f)).padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, Modifier.size(24.dp), color); Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Txt(sub.str("status_display"), weight = FontWeight.SemiBold, size = 15.sp)
                Muted("${sub.str("submitted_at")}${if (sub.int("version") > 1) " · ${t("versiya")} ${sub.int("version")}" else ""}", translate = false)
            }
            val grade = if (sub.isNull("effective_grade")) sub.opt("grade") else sub.opt("effective_grade")
            if (grade != null && grade != JSONObject.NULL) Txt("$grade/${sub.int("max_score")}", size = 20.sp, weight = FontWeight.Bold, color = color, translate = false)
        }
        if (sub.bool("is_late")) { Spacer(Modifier.height(8.dp)); TagAmber("Keç topşirilgan") }
        sub.strOrNull("file_name")?.let {
            Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.AttachFile, null, Modifier.size(16.dp), pal.muted); Spacer(Modifier.width(5.dp))
                Muted(it, lines = 1, translate = false)
            }
        }
        sub.strOrNull("text_content")?.let { RichText(it, Modifier.padding(top = 10.dp), 13.5.sp) }
        if (sub.int("coins_earned") > 0) Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            CoinDot(18.dp); Spacer(Modifier.width(6.dp))
            Txt("+${num(sub.int("coins_earned"))} coin", weight = FontWeight.SemiBold, color = pal.amber, translate = false)
        }
        sub.strOrNull("feedback")?.let {
            Spacer(Modifier.height(10.dp)); Hairline(); Spacer(Modifier.height(10.dp))
            Txt("Öqituvçi izohi", weight = FontWeight.SemiBold, size = 13.sp)
            RichText(it, Modifier.padding(top = 4.dp), 13.5.sp)
        }
        sub.strOrNull("ai_feedback")?.let {
            Spacer(Modifier.height(10.dp)); Hairline(); Spacer(Modifier.height(10.dp))
            Txt("AI xulosasi", weight = FontWeight.SemiBold, size = 13.sp)
            RichText(it, Modifier.padding(top = 4.dp), 13.5.sp)
        }
        if (sub.bool("can_edit")) {
            val mins = sub.int("edit_seconds_left") / 60
            Muted("${t("Tahrirlaş uçun qolgan vaqt")}: $mins ${t("daqiqa")}", Modifier.padding(top = 10.dp), translate = false)
        }
    }
}

@Composable
private fun SubmitForm(lessonId: Int, hw: JSONObject, action: String, label: String, existing: JSONObject?, onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    val fileOnly = hw.bool("file_only") || hw.bool("handwritten_only")
    var mode by remember { mutableIntStateOf(if (fileOnly || existing?.str("submission_type") == "file") 1 else 0) }
    var text by remember { mutableStateOf("") }
    var file by remember { mutableStateOf<PickedFile?>(null) }
    var busy by remember { mutableStateOf(false) }
    val pick = rememberFilePicker(HOMEWORK_MAX_BYTES) { file = it }

    Column(Modifier.fillMaxWidth().card().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (!fileOnly) Segmented(listOf("Matn", "Fayl"), mode) { mode = it }
        if (mode == 0) Field(text, { text = it }, "Javobingizni yozing…", single = false, minHeight = 130.dp)
        else {
            Row(
                Modifier.fillMaxWidth().press(scale = .98f) { pick(if (hw.bool("handwritten_only")) "image/*" else "*/*") }
                    .clip(RoundedCornerShape(14.dp)).background(pal.surface).border(1.dp, pal.border, RoundedCornerShape(14.dp)).padding(14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(if (hw.bool("handwritten_only")) Icons.Rounded.Image else Icons.Rounded.AttachFile, null, Modifier.size(22.dp), pal.a1)
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    val f = file
                    if (f != null) {
                        Txt(f.name, weight = FontWeight.Medium, lines = 1, translate = false)
                        Muted("${f.bytes.size / 1024} KB", translate = false)
                    } else {
                        Txt(if (hw.bool("handwritten_only")) "Yozma ish rasmini tanlang" else "Fayl tanlang", weight = FontWeight.Medium)
                        Muted("Eng köpi 5 MB")
                    }
                }
            }
        }
        val valid = if (mode == 0) text.trim().length >= 10 else file != null
        if (mode == 0 && text.isNotEmpty() && !valid) Muted("Matn kamida 10 belgi bölsin")
        Btn(label, Modifier.fillMaxWidth(), BtnKind.Primary, Icons.Rounded.Send, enabled = valid, busy = busy) {
            busy = true
            scope.launch {
                try {
                    val r = if (mode == 0) Api.upload(
                        "/api/v1/app/lessons/$lessonId/homework/$action/",
                        mapOf("submission_type" to "text", "text_content" to text.trim()),
                    ) else Api.upload(
                        "/api/v1/app/lessons/$lessonId/homework/$action/",
                        mapOf("submission_type" to "file"), "file", file,
                    )
                    Toasts.show(r.str("message").ifEmpty { "Vazifa yuborildi" }, "ok")
                    AppState.refreshUser()
                    onDone()
                } catch (e: ApiError) {
                    Toasts.show(e.message ?: "", "err")
                }
                busy = false
            }
        }
    }
}

@Composable
private fun HomeworkChat(lessonId: Int) {
    val scope = rememberCoroutineScope()
    var text by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var tick by remember { mutableIntStateOf(0) }
    val load = rememberLoad(tick) { Api.rows(Api.get("/api/v1/app/lessons/$lessonId/homework/messages/", fresh = true).optJSONArray("messages")) }
    Column(Modifier.fillMaxWidth().card().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Rounded.ChatBubble, null, Modifier.size(18.dp), pal.text); Spacer(Modifier.width(8.dp))
            Txt("Öqituvçi bilan yozişma", weight = FontWeight.SemiBold)
        }
        load.data?.forEach { m ->
            key(m.int("id")) { Bubble(stripHtml(m.str("message")), m.str("created_at"), m.bool("is_me"), if (m.bool("is_me")) null else m.str("sender"), m.strOrNull("file_url")) }
        }
        if (load.data?.isEmpty() == true) Muted("Hali xabar yöq")
        Field(
            text, { text = it }, "Xabar yozing…",
            trailing = {
                Box(Modifier.size(34.dp).press(enabled = text.isNotBlank() && !sending) {
                    sending = true
                    scope.launch {
                        try {
                            Api.upload("/api/v1/app/lessons/$lessonId/homework/messages/send/", mapOf("message" to text.trim()))
                            text = ""
                            tick++
                        } catch (e: ApiError) { Toasts.show(e.message ?: "", "err") }
                        sending = false
                    }
                }, contentAlignment = Alignment.Center) {
                    if (sending) Spinner(18.dp) else Icon(Icons.Rounded.Send, t("Yuboriş"), Modifier.size(20.dp), if (text.isNotBlank()) pal.a1 else pal.muted)
                }
            },
        )
    }
}

// ───────── Speaking ─────────
@Composable
private fun SpeakingContent(d: JSONObject, c: JSONObject, reload: () -> Unit) {
    val sub = c.optJSONObject("submission")
    Column(Modifier.fillMaxWidth().card().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IcoBox(Icons.Rounded.Mic, pal.a1); Spacer(Modifier.width(10.dp))
            Txt("Speaking vazifa", Modifier.weight(1f), 15.sp, FontWeight.SemiBold)
            Tag(c.str("target_level"), translate = false)
        }
        Spacer(Modifier.height(10.dp))
        RichText(c.str("description"))
        c.strOrNull("criteria")?.let {
            Spacer(Modifier.height(10.dp))
            Txt("Baholaş mezonlari", size = 13.sp, weight = FontWeight.SemiBold)
            Muted(it, Modifier.padding(top = 2.dp), translate = false)
        }
        Muted("${t("Eng uzun yozuv")}: ${c.int("max_duration")} ${t("soniya")}", Modifier.padding(top = 8.dp), translate = false)
    }
    if (sub != null) SpeakingResult(sub) else SpeakingRecorder(d.int("id"), c.int("max_duration").coerceAtLeast(10), reload)
}

@Composable
private fun SpeakingResult(sub: JSONObject) {
    Column(Modifier.fillMaxWidth().card().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Txt(sub.str("status_display"), weight = FontWeight.SemiBold, size = 15.sp)
                Muted(dateText(sub.str("submitted_at")), translate = false)
            }
            if (!sub.isNull("grade")) Txt("${sub.int("grade")}", size = 22.sp, weight = FontWeight.Bold, color = pal.green, translate = false)
        }
        sub.strOrNull("audio_url")?.let { AudioPlayerButton(it) }
        listOf("pronunciation" to "Talaffuz", "fluency" to "Ravonlik", "grammar" to "Grammatika", "vocabulary" to "Luğat").forEach { (k, label) ->
            if (!sub.isNull(k)) Column {
                Row {
                    Muted(label, Modifier.weight(1f))
                    Txt("${sub.int(k)}", size = 12.5.sp, weight = FontWeight.SemiBold, translate = false)
                }
                Spacer(Modifier.height(4.dp))
                ProgressBar(sub.int(k) / 100f)
            }
        }
        sub.strOrNull("feedback")?.let { Txt("Öqituvçi izohi", size = 13.sp, weight = FontWeight.SemiBold); Muted(stripHtml(it), translate = false) }
        sub.strOrNull("ai_feedback")?.let { Txt("AI xulosasi", size = 13.sp, weight = FontWeight.SemiBold); Muted(stripHtml(it), translate = false) }
        sub.strOrNull("transcript")?.let { Txt("Matn", size = 13.sp, weight = FontWeight.SemiBold); Muted(it, translate = false) }
    }
}

@Composable
private fun AudioPlayerButton(source: String) {
    var player by remember { mutableStateOf<MediaPlayer?>(null) }
    fun stop() { runCatching { player?.stop() }; player?.release(); player = null }
    DisposableEffect(Unit) { onDispose { stop() } }
    Btn(if (player == null) "Yozuvni tinglaş" else "Töxtatiş", small = true, icon = if (player == null) Icons.Rounded.PlayArrow else Icons.Rounded.Stop) {
        if (player != null) stop()
        else runCatching {
            player = MediaPlayer().apply {
                setDataSource(source)
                setOnPreparedListener { it.start() }
                setOnCompletionListener { stop() }
                setOnErrorListener { _, _, _ -> stop(); Toasts.show("Audioni oçib bölmadi", "err"); true }
                prepareAsync()
            }
        }.onFailure { Toasts.show("Audioni oçib bölmadi", "err") }
    }
}

@Composable
private fun SpeakingRecorder(lessonId: Int, maxSeconds: Int, onDone: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val output = remember { File(ctx.cacheDir, "speaking_$lessonId.m4a") }
    var recorder by remember { mutableStateOf<MediaRecorder?>(null) }
    var startedAt by remember { mutableStateOf(0L) }
    var elapsed by remember { mutableIntStateOf(0) }
    var recorded by remember { mutableStateOf<PickedFile?>(null) }
    var duration by remember { mutableIntStateOf(0) }
    var busy by remember { mutableStateOf(false) }

    fun stopRecording() {
        val r = recorder ?: return
        recorder = null
        val ok = runCatching { r.stop() }.isSuccess
        r.release()
        if (ok && output.length() in 1..AUDIO_MAX_BYTES.toLong()) {
            duration = elapsed
            recorded = PickedFile("speaking.m4a", "audio/mp4", output.readBytes())
        } else Toasts.show(if (ok) "Yozuv juda katta" else "Yozuv juda qisqa, qayta urinib köring", "err")
    }
    fun startRecording() {
        recorded = null
        elapsed = 0
        runCatching {
            @Suppress("DEPRECATION")
            val r = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) MediaRecorder(ctx) else MediaRecorder()
            r.setAudioSource(MediaRecorder.AudioSource.MIC)
            r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            r.setAudioEncodingBitRate(64_000)
            r.setAudioSamplingRate(44_100)
            r.setOutputFile(output.absolutePath)
            r.prepare()
            r.start()
            recorder = r
            startedAt = SystemClock.elapsedRealtime()
        }.onFailure { Toasts.show("Mikrofonni yoqib bölmadi", "err") }
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) startRecording() else Toasts.show("Yozib oliş uçun mikrofon ruxsati kerak", "info")
    }
    val pick = rememberFilePicker(AUDIO_MAX_BYTES) { recorded = it; duration = 0 }

    LaunchedEffect(recorder) {
        while (recorder != null) {
            elapsed = ((SystemClock.elapsedRealtime() - startedAt) / 1000).toInt()
            if (elapsed >= maxSeconds) { stopRecording(); break }
            delay(250)
        }
    }
    DisposableEffect(Unit) {
        onDispose {
            recorder?.let { runCatching { it.stop() }; it.release() }
            output.delete()
        }
    }

    val isRec = recorder != null
    Column(Modifier.fillMaxWidth().card().padding(18.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(
            Modifier.size(84.dp).press(scale = .92f) {
                when {
                    isRec -> stopRecording()
                    ctx.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED -> startRecording()
                    else -> permission.launch(Manifest.permission.RECORD_AUDIO)
                }
            }.clip(CircleShape).background(if (isRec) pal.red else pal.a1),
            contentAlignment = Alignment.Center,
        ) { Icon(if (isRec) Icons.Rounded.Stop else Icons.Rounded.Mic, t(if (isRec) "Töxtatiş" else "Yozib oliş"), Modifier.size(38.dp), Color.White) }
        Txt(
            if (isRec) "$elapsed / $maxSeconds s" else if (recorded != null) "Yozuv tayyor" else "Bosing va gapiring",
            weight = FontWeight.SemiBold, translate = !isRec,
        )
        val rec = recorded
        if (rec != null) {
            Muted("${rec.name} · ${rec.bytes.size / 1024} KB", translate = false)
            if (rec.name == "speaking.m4a" && output.exists()) AudioPlayerButton(output.absolutePath)
            Btn("Topşiriş", Modifier.fillMaxWidth(), BtnKind.Primary, Icons.Rounded.Send, busy = busy) {
                busy = true
                scope.launch {
                    try {
                        val r = Api.upload("/api/v1/app/lessons/$lessonId/speaking/", mapOf("duration" to duration.toString()), "audio_file", rec)
                        Toasts.show(if (r.bool("ai_check")) "Topşirildi. AI bir neça daqiqada tekşiradi" else "Speaking vazifa topşirildi", "ok")
                        onDone()
                    } catch (e: ApiError) {
                        Toasts.show(e.message ?: "", "err")
                    }
                    busy = false
                }
            }
        }
        if (!isRec) Btn("Audio fayl tanlaş", small = true, icon = Icons.Rounded.AudioFile) { pick("audio/*") }
    }
}

// ───────── Test ─────────
private class TestQ(val id: Int, val type: String, val text: String, val image: String?, val options: List<Pair<Int, String>>)

private class TestSession(
    val questions: List<TestQ>,
    val remaining: Int,
    val attemptId: Int? = null,
    val token: String? = null,
)

private fun questionsFromQuiz(arr: JSONArray?): List<TestQ> = Api.rows(arr).map { q ->
    TestQ(
        q.int("id"), q.str("type"), q.str("text"), q.strOrNull("image"),
        Api.rows(q.optJSONArray("options")).map { it.int("id") to it.str("text") },
    )
}

private fun questionsFromLegacy(arr: JSONArray?): List<TestQ> = Api.rows(arr).map { q ->
    TestQ(q.int("id"), "single_choice", q.str("text"), q.strOrNull("image"), Api.rows(q.optJSONArray("answers")).map { it.int("id") to it.str("text") })
}

@Composable
private fun TestLessonContent(d: JSONObject, c: JSONObject?, reload: () -> Unit) {
    val lessonId = d.int("id")
    var session by remember { mutableStateOf<TestSession?>(null) }
    var initialAnswers by remember { mutableStateOf<Map<Int, Set<Int>>>(emptyMap()) }
    var initialTexts by remember { mutableStateOf<Map<Int, String>>(emptyMap()) }
    var result by remember { mutableStateOf<JSONObject?>(null) }

    val running = session
    val finished = result
    when {
        c == null -> Page(bottom = 40.dp) {
            BackHeader(d.str("title"), onBack = { AppState.back() })
            EmptyState(Icons.Rounded.HourglassEmpty, "Bu test hali tayyor emas")
        }
        finished != null -> Page(bottom = 40.dp) {
            BackHeader(d.str("title"), onBack = { AppState.back() })
            TestResultCard(finished)
            LessonNextButton(d, enabled = finished.bool("passed"))
            if (!finished.bool("passed") || c.bool("allow_retry")) Btn("Test sahifasiga qaytiş", Modifier.fillMaxWidth(), icon = Icons.Rounded.Refresh) {
                result = null
                reload()
            }
        }
        running != null -> TestRunner(
            lessonId, c.str("engine"), d.str("title"), running, initialAnswers, initialTexts,
            onFinished = { r -> session = null; result = r; AppScope.launch { AppState.refreshUser() } },
            onExit = { session = null; reload() },
        )
        else -> Page(bottom = 40.dp) {
            BackHeader(d.str("title"), d.optJSONObject("course")?.str("name"), onBack = { AppState.back() })
            TestIntro(lessonId, c, onStart = { s, a, x -> initialAnswers = a; initialTexts = x; session = s }, onShowResult = { result = it })
            LessonNextButton(d, enabled = d.bool("completed"))
        }
    }
}

@Composable
private fun TestIntro(
    lessonId: Int,
    c: JSONObject,
    onStart: (TestSession, Map<Int, Set<Int>>, Map<Int, String>) -> Unit,
    onShowResult: (JSONObject) -> Unit,
) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    val quiz = c.str("engine") == "quiz"
    val last = c.optJSONObject("last_result")
    val isFinal = c.bool("is_final")
    val blocked = c.strOrNull("blocked_reason")
    val resumeLegacy = !quiz && Settings.testState(lessonId) != null
    val resume = c.bool("resume") || resumeLegacy
    val retry = last != null && !resume
    val paymentStatus = c.strOrNull("payment_status")
    val needsPayment = retry && isFinal && paymentStatus != "approved"
    val noRetry = retry && !isFinal && !c.bool("allow_retry")
    val allowed = c.int("attempts_allowed")
    val attemptsUsed = quiz && retry && !isFinal && allowed > 0 && c.int("prior_attempts") >= allowed

    suspend fun openPaymentOr(e: ApiError): Boolean {
        val path = e.data?.strOrNull("payment_path") ?: return false
        openBrowser(ctx, Api.webUrl(path))
        return true
    }

    fun begin() {
        busy = true
        scope.launch {
            try {
                if (quiz) {
                    val r = Api.post("/api/v1/quiz/attempts/", JSONObject().put("quiz_id", c.int("quiz_id")))
                    val answers = HashMap<Int, Set<Int>>()
                    val texts = HashMap<Int, String>()
                    Api.rows(r.optJSONArray("questions")).forEach { q ->
                        val saved = q.optJSONObject("saved_response") ?: return@forEach
                        saved.optJSONArray("selected_option_ids")?.let { a -> answers[q.int("id")] = (0 until a.length()).map { a.getInt(it) }.toSet() }
                        saved.strOrNull("text")?.let { texts[q.int("id")] = it }
                    }
                    onStart(TestSession(questionsFromQuiz(r.optJSONArray("questions")), r.int("remaining_seconds"), attemptId = r.int("id")), answers, texts)
                } else {
                    val saved = Settings.testState(lessonId)
                    val body = JSONObject()
                    saved?.strOrNull("attempt")?.let { body.put("attempt", it) }
                    val r = Api.post("/api/v1/app/lessons/$lessonId/test/start/", body)
                    val token = r.str("attempt")
                    val answers = HashMap<Int, Set<Int>>()
                    if (saved?.strOrNull("attempt") == token) {
                        saved.optJSONObject("answers")?.let { a -> a.keys().forEach { k -> answers[k.toInt()] = setOf(a.getInt(k)) } }
                    } else Settings.saveTestState(lessonId, JSONObject().put("attempt", token))
                    onStart(TestSession(questionsFromLegacy(r.optJSONArray("questions")), r.int("remaining_seconds"), token = token), answers, emptyMap())
                }
            } catch (e: ApiError) {
                if (e.status == 402 || e.code == "payment_required") {
                    if (!openPaymentOr(e)) c.strOrNull("payment_path")?.let { openBrowser(ctx, Api.webUrl(it)) }
                    Toasts.show(e.message ?: "", "info")
                } else Toasts.show(e.message ?: "", "err")
            }
            busy = false
        }
    }

    Column(Modifier.fillMaxWidth().card().padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IcoBox(Icons.Rounded.TaskAlt, pal.green); Spacer(Modifier.width(10.dp))
            Txt(c.str("title"), Modifier.weight(1f), 16.sp, FontWeight.SemiBold, translate = false)
            if (isFinal) TagAmber("Yakuniy test")
        }
        c.strOrNull("description")?.let { Muted(stripHtml(it), translate = false) }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            InfoTile("Savollar", num(c.int("question_count")), Modifier.weight(1f))
            InfoTile("Vaqt", "${c.int("time_limit_minutes")} ${t("daq")}", Modifier.weight(1f))
            InfoTile("Ötiş bali", "${c.int("passing_score")}%", Modifier.weight(1f))
        }
    }

    if (last != null) Row(Modifier.fillMaxWidth().card(fill = (if (last.bool("passed")) pal.green else pal.red).copy(alpha = .11f)).padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
        Ring(last.int("score"), 52.dp, if (last.bool("passed")) pal.green else pal.red)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Txt(if (last.bool("passed")) "Testdan ötgansiz" else "Oxirgi uriniş ötmagan", weight = FontWeight.SemiBold)
            Muted("${num(last.int("correct"))} / ${num(last.int("total"))} ${t("töğri javob")}", translate = false)
        }
        var opening by remember { mutableStateOf(false) }
        Btn("Tahlil", small = true, busy = opening) {
            opening = true
            scope.launch {
                try {
                    onShowResult(
                        if (quiz) quizReview(c.int("last_attempt_id"))
                        else Api.get("/api/v1/app/lessons/$lessonId/test/result/", fresh = true),
                    )
                } catch (e: ApiError) { Toasts.show(e.message ?: "", "err") }
                opening = false
            }
        }
    }

    when {
        blocked != null -> Row(Modifier.fillMaxWidth().card(fill = pal.amber.copy(alpha = .13f)).padding(14.dp)) { Txt(blocked, translate = false) }
        noRetry || attemptsUsed -> Muted(if (noRetry) "Bu testni qayta topşirib bölmaydi." else "Urinişlar soni tugagan.", size = 13.5.sp)
        needsPayment -> {
            val text = when (paymentStatus) {
                "pending" -> "Tölov çeki tekşirilmoqda. Tasdiqlangaç testni qayta topşirişingiz mumkin."
                "rejected" -> "Oldingi tölov rad etilgan. Yangi çek yuklang."
                else -> "Yakuniy testni qayta topşiriş uçun tölov kerak."
            }
            Muted(text, size = 13.5.sp)
            if (paymentStatus != "pending") c.strOrNull("payment_path")?.let { OpenSiteButton("Tölov sahifasi", it) }
        }
        else -> {
            val label = when { resume -> "Testni davom ettiriş"; retry -> "Qayta topşiriş"; else -> "Testni boşlaş" }
            Btn(label, Modifier.fillMaxWidth(), BtnKind.Primary, Icons.Rounded.PlayArrow, busy = busy) {
                if (retry && !isFinal) {
                    Sheets.confirm("Qayta topşiriş", "${t("Qayta uriniş narxi")}: ${c.int("retry_cost")} coin", "Davom etiş") { begin() }
                } else begin()
            }
        }
    }
}

private suspend fun quizReview(attemptId: Int): JSONObject {
    val r = Api.get("/api/v1/quiz/attempts/$attemptId/review/", fresh = true)
    val rows = JSONArray()
    Api.rows(r.optJSONArray("questions")).forEach { q ->
        val options = Api.rows(q.optJSONArray("options"))
        val response = q.optJSONObject("response")
        val picked = response?.optJSONArray("selected_option_ids")?.let { a -> (0 until a.length()).map { a.getInt(it) } }.orEmpty()
        val selected = options.filter { it.int("id") in picked }.joinToString(", ") { it.str("text") }.ifEmpty { response?.strOrNull("text").orEmpty() }
        val right = options.filter { it.bool("is_correct") }.map { it.str("text") } +
            (q.optJSONArray("correct_answers")?.let { a -> (0 until a.length()).map { a.getString(it) } }.orEmpty())
        val correct = if (q.isNull("is_correct")) null else q.bool("is_correct")
        rows.put(
            JSONObject().put("question", q.str("text")).put("is_correct", correct ?: JSONObject.NULL)
                .put("selected", selected.ifEmpty { JSONObject.NULL })
                .put("correct_answer", if (correct == true) JSONObject.NULL else right.joinToString(", ").ifEmpty { JSONObject.NULL })
                .put("explanation", if (correct == true) JSONObject.NULL else q.strOrNull("explanation") ?: JSONObject.NULL)
                .put("feedback", q.strOrNull("feedback") ?: JSONObject.NULL),
        )
    }
    return JSONObject().put("score", r.int("score")).put("passed", r.bool("passed")).put("correct", r.int("correct_count"))
        .put("total", r.int("total_questions")).put("answers", rows).put("coins", r.int("coins_earned"))
        .put("manual", r.str("status") == "submitted")
}

@Composable
private fun InfoTile(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier.clip(RoundedCornerShape(14.dp)).background(pal.surface).padding(10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Txt(value, size = 15.sp, weight = FontWeight.Bold, lines = 1, translate = false)
        Muted(label, size = 11.5.sp, lines = 1)
    }
}

@Composable
private fun TestRunner(
    lessonId: Int,
    engine: String,
    title: String,
    s: TestSession,
    initialAnswers: Map<Int, Set<Int>>,
    initialTexts: Map<Int, String>,
    onFinished: (JSONObject) -> Unit,
    onExit: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    val quiz = engine == "quiz"
    val answers = remember { mutableStateMapOf<Int, Set<Int>>().apply { putAll(initialAnswers) } }
    val texts = remember { mutableStateMapOf<Int, String>().apply { putAll(initialTexts) } }
    val dirty = remember { mutableStateMapOf<Int, Boolean>() }
    var index by remember { mutableIntStateOf(0) }
    var sending by remember { mutableStateOf(false) }
    var failed by remember { mutableStateOf(false) }
    val deadline = remember { SystemClock.elapsedRealtime() + s.remaining * 1000L }
    var left by remember { mutableIntStateOf(s.remaining) }

    fun answered(q: TestQ) = answers[q.id].orEmpty().isNotEmpty() || !texts[q.id].isNullOrBlank()

    suspend fun saveQuizAnswer(q: TestQ): Boolean {
        val response = if (q.options.isNotEmpty()) JSONObject().put("selected_option_ids", JSONArray(answers[q.id].orEmpty().toList()))
        else JSONObject().put("text", texts[q.id].orEmpty())
        return try {
            Api.post("/api/v1/quiz/attempts/${s.attemptId}/answer/", JSONObject().put("question_id", q.id).put("response", response))
            dirty.remove(q.id)
            true
        } catch (e: ApiError) {
            dirty[q.id] = true
            false
        }
    }

    fun persistLegacy() {
        val a = JSONObject()
        answers.forEach { (k, v) -> v.firstOrNull()?.let { a.put(k.toString(), it) } }
        Settings.saveTestState(lessonId, JSONObject().put("attempt", s.token).put("answers", a))
    }

    fun submit() {
        if (sending) return
        sending = true
        failed = false
        scope.launch {
            try {
                val result = if (quiz) {
                    s.questions.filter { dirty[it.id] == true }.forEach { saveQuizAnswer(it) }
                    Api.post("/api/v1/quiz/attempts/${s.attemptId}/submit/")
                    quizReview(s.attemptId!!)
                } else {
                    val a = JSONObject()
                    answers.forEach { (k, v) -> v.firstOrNull()?.let { a.put(k.toString(), it) } }
                    val r = Api.post("/api/v1/app/lessons/$lessonId/test/submit/", JSONObject().put("attempt", s.token).put("answers", a))
                    Settings.saveTestState(lessonId, null)
                    r
                }
                onFinished(result)
            } catch (e: ApiError) {
                failed = true
                Toasts.show(e.message ?: "", "err")
            }
            sending = false
        }
    }

    LaunchedEffect(Unit) {
        while (true) {
            left = ((deadline - SystemClock.elapsedRealtime()) / 1000).toInt().coerceAtLeast(0)
            if (left == 0) { if (!failed) submit(); break }
            delay(500)
        }
    }

    BackHandler {
        Sheets.confirm("Testdan çiqasizmi?", "Javoblar saqlanadi, lekin vaqt tuğamaydi. Keyinroq davom ettirişingiz mumkin.", "Çiqiş", danger = true) { onExit() }
    }

    val q = s.questions.getOrNull(index)
    Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding()) {
        Row(Modifier.padding(start = 16.dp, end = 16.dp, top = 10.dp, bottom = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Txt(title, weight = FontWeight.SemiBold, lines = 1, translate = false)
                Muted("${t("Savol")} ${index + 1} / ${s.questions.size}", translate = false)
            }
            val low = left <= 60
            Row(
                Modifier.clip(RoundedCornerShape(20.dp)).background((if (low) pal.red else pal.a1).copy(alpha = .15f)).padding(horizontal = 12.dp, vertical = 7.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Rounded.Timer, null, Modifier.size(16.dp), if (low) pal.red else pal.a1)
                Spacer(Modifier.width(5.dp))
                Txt("${left / 60}:${(left % 60).toString().padStart(2, '0')}", weight = FontWeight.Bold, color = if (low) pal.red else pal.a1, translate = false)
            }
        }
        ProgressBar(answers.size.toFloat().plus(texts.count { it.value.isNotBlank() }) / s.questions.size.coerceAtLeast(1), Modifier.padding(horizontal = 16.dp), height = 5.dp)
        if (q == null) {
            EmptyState(Icons.Rounded.HourglassEmpty, "Bu testda hali savollar yöq")
            return@Column
        }
        Column(
            Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            key(q.id) {
                Txt(q.text, size = 17.sp, weight = FontWeight.SemiBold, translate = false)
                Api.media(q.image)?.let { AsyncImage(it, null, Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)), contentScale = ContentScale.FillWidth) }
                val multi = q.type == "multiple_choice"
                if (multi) Muted("Bir neça javob tanlash mumkin")
                if (q.options.isEmpty()) {
                    Field(
                        texts[q.id].orEmpty(),
                        { v ->
                            texts[q.id] = v
                            dirty[q.id] = true
                        },
                        "Javobingizni yozing…", single = q.type == "short_answer", minHeight = if (q.type == "essay") 160.dp else 46.dp,
                    )
                } else q.options.forEach { (oid, text) ->
                    val on = oid in answers[q.id].orEmpty()
                    Row(
                        Modifier.fillMaxWidth().press(scale = .98f) {
                            val cur = answers[q.id].orEmpty()
                            answers[q.id] = if (multi) (if (on) cur - oid else cur + oid) else setOf(oid)
                            if (quiz) scope.launch { saveQuizAnswer(q) } else persistLegacy()
                        }.clip(RoundedCornerShape(14.dp)).background(if (on) pal.a1.copy(alpha = .16f) else pal.surface)
                            .border(1.dp, if (on) pal.a1 else pal.border, RoundedCornerShape(14.dp)).padding(14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            when {
                                multi && on -> Icons.Rounded.CheckBox
                                multi -> Icons.Rounded.CheckBoxOutlineBlank
                                on -> Icons.Rounded.RadioButtonChecked
                                else -> Icons.Rounded.RadioButtonUnchecked
                            },
                            null, Modifier.size(22.dp), if (on) pal.a1 else pal.muted,
                        )
                        Spacer(Modifier.width(10.dp))
                        Txt(text, Modifier.weight(1f), translate = false)
                    }
                }
            }
        }
        Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            fun leave() {
                val cur = s.questions[index]
                if (quiz && dirty[cur.id] == true) scope.launch { saveQuizAnswer(cur) }
            }
            if (index > 0) Btn("Orqaga", Modifier.weight(1f), icon = Icons.Rounded.ChevronLeft) { leave(); index-- }
            if (index < s.questions.lastIndex) Btn("Keyingi", Modifier.weight(1f), BtnKind.Primary) { leave(); index++ }
            else Btn(if (failed) "Qayta yuboriş" else "Yakunlaş", Modifier.weight(1f), BtnKind.Primary, Icons.Rounded.Check, busy = sending) {
                leave()
                val empty = s.questions.count { !answered(it) }
                if (empty > 0) Sheets.confirm("Testni yakunlaysizmi?", "${t("Javobsiz savollar")}: $empty", "Yakunlaş") { submit() }
                else submit()
            }
        }
    }
}

@Composable
private fun TestResultCard(r: JSONObject) {
    val passed = r.bool("passed")
    val manual = r.bool("manual")
    val color = if (manual) pal.amber else if (passed) pal.green else pal.red
    Column(Modifier.fillMaxWidth().card(fill = color.copy(alpha = .11f)).padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Ring(r.int("score"), 96.dp, color, 20.sp)
        Spacer(Modifier.height(10.dp))
        Txt(
            if (manual) "Öqituvçi tekşiruvi kutilmoqda" else if (passed) "Tabriklaymiz! Testdan ötdingiz" else "Testdan öta olmadingiz",
            size = 18.sp, weight = FontWeight.Bold,
        )
        Muted("${num(r.int("correct"))} / ${num(r.int("total"))} ${t("töğri javob")}", Modifier.padding(top = 2.dp), translate = false)
        val coins = r.int("coins").takeIf { it > 0 } ?: if (r.bool("coin_awarded")) r.int("correct") else 0
        if (coins > 0) Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            CoinDot(20.dp); Spacer(Modifier.width(6.dp))
            Txt("+${num(coins)} coin", weight = FontWeight.Bold, color = pal.amber, translate = false)
        }
    }
    val wrong = Api.rows(r.optJSONArray("answers")).filter { it.isNull("is_correct") || !it.bool("is_correct") }
    if (wrong.isNotEmpty()) {
        SectionTitle("Notöğri javoblar tahlili", Icons.Rounded.Rule)
        wrong.forEachIndexed { i, a ->
            Column(Modifier.fillMaxWidth().card().padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Txt("${i + 1}. ${a.str("question")}", weight = FontWeight.SemiBold, translate = false)
                Api.media(a.strOrNull("image"))?.let { AsyncImage(it, null, Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)), contentScale = ContentScale.FillWidth) }
                Row {
                    Muted("${t("Sizning javobingiz")}: ", translate = false)
                    Txt(a.strOrNull("selected") ?: t("Javob tanlanmagan"), size = 12.5.sp, color = pal.red, translate = false)
                }
                a.strOrNull("correct_answer")?.let {
                    Row {
                        Muted("${t("Töğri javob")}: ", translate = false)
                        Txt(it, size = 12.5.sp, color = pal.green, translate = false, modifier = Modifier.weight(1f))
                    }
                }
                a.strOrNull("explanation")?.let { Muted(it, translate = false) }
                a.strOrNull("feedback")?.let { Muted(it, translate = false) }
            }
        }
    }
}
