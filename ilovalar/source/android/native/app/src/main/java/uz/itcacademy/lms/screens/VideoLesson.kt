package uz.itcacademy.lms.screens

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.pm.ActivityInfo
import android.net.Uri
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
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
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import uz.itcacademy.lms.*
import uz.itcacademy.lms.ui.*
import kotlin.coroutines.resume

private const val SAMPLE_MS = 1000L
private const val SYNC_MS = 10_000L
private const val QUIZ_ANSWER_SECONDS = 35
private const val QUIZ_AUTO_CONTINUE_SECONDS = 7
private const val PLAYER_ORIGIN = "https://itc-academy.uz/"

private data class PlayerState(val time: Double, val duration: Double, val playing: Boolean, val ready: Boolean, val error: Int)

private fun jsonSegments(arr: JSONArray?): List<Seg> {
    if (arr == null) return emptyList()
    return Segments.normalize((0 until arr.length()).mapNotNull { i ->
        arr.optJSONArray(i)?.let { Seg(it.optDouble(0), it.optDouble(1)) }
    })
}

private fun clock(seconds: Double): String {
    val s = kotlin.math.max(0, kotlin.math.round(seconds).toInt())
    return "${s / 60}:${(s % 60).toString().padStart(2, '0')}"
}

/**
 * Faqat video kadri uchun kichik oyna: YouTube/Vimeo shu tarzda ijro etiladi, qolgan butun ekran native.
 * JavaScript ko'prigi yo'q: ilova holatni o'zi so'raydi, shuning uchun sahifa ilova ichidagi hech narsaga tega olmaydi.
 * Video kadridan tashqariga olib ketadigan havolalar tizim brauzerida ochiladi.
 */
@SuppressLint("SetJavaScriptEnabled")
private class PlayerFrame(ctx: Context, provider: String, videoId: String?, embedUrl: String?, resumeAt: Double) {
    var custom by mutableStateOf<View?>(null)
    private var customCallback: WebChromeClient.CustomViewCallback? = null

    val web = WebView(ctx).apply {
        setBackgroundColor(android.graphics.Color.BLACK)
        layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            allowFileAccess = false
            allowContentAccess = false
            setSupportMultipleWindows(false)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        }
        CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)
        webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                if (!request.isForMainFrame) return false
                openBrowser(view.context, request.url.toString())
                return true
            }
        }
        webChromeClient = object : WebChromeClient() {
            override fun onShowCustomView(view: View, callback: CustomViewCallback) {
                custom = view
                customCallback = callback
            }
            override fun onHideCustomView() {
                custom = null
                customCallback = null
            }
        }
        loadDataWithBaseURL(PLAYER_ORIGIN, playerHtml(provider, videoId, embedUrl, resumeAt), "text/html", "utf-8", null)
    }

    fun exitFullscreen() { customCallback?.onCustomViewHidden(); custom = null; customCallback = null }
    fun pause() = web.evaluateJavascript("window.itc&&itc.pause()", null)
    fun play() = web.evaluateJavascript("window.itc&&itc.play()", null)
    fun seek(t: Double) = web.evaluateJavascript("window.itc&&itc.seek($t)", null)

    suspend fun read(): PlayerState? = suspendCancellableCoroutine { c ->
        web.evaluateJavascript("window.itc?itc.state():null") { raw ->
            val parsed = runCatching {
                val o = JSONObject(JSONTokener(raw).nextValue() as String)
                PlayerState(o.optDouble("t", 0.0), o.optDouble("d", 0.0), o.optBoolean("p"), o.optBoolean("r"), o.optInt("e"))
            }.getOrNull()
            if (c.isActive) c.resume(parsed)
        }
    }

    fun destroy() {
        web.stopLoading()
        web.loadUrl("about:blank")
        (web.parent as? ViewGroup)?.removeView(web)
        web.destroy()
    }
}

private fun playerHtml(provider: String, videoId: String?, embedUrl: String?, resumeAt: Double): String {
    val start = kotlin.math.floor(resumeAt).toInt()
    val shared = """
        var S={t:0,d:0,p:false,r:false,e:0},P=null;
        window.itc={state:function(){if(window.read)read();return JSON.stringify(S)},
          play:function(){if(window.doPlay)doPlay()},pause:function(){if(window.doPause)doPause()},
          seek:function(t){if(window.doSeek)doSeek(t)}};
    """
    val body = if (provider == "vimeo") {
        val src = JSONObject.quote(
            Uri.parse(embedUrl.orEmpty()).buildUpon().appendQueryParameter("controls", "1").appendQueryParameter("playsinline", "1").build().toString(),
        )
        """
        <iframe id="v" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe>
        <script>$shared
        document.getElementById('v').src=$src;
        var s=document.createElement('script');s.src='https://player.vimeo.com/api/player.js';
        s.onerror=function(){S.e=-1};
        s.onload=function(){P=new Vimeo.Player(document.getElementById('v'));
          window.doPlay=function(){P.play().catch(function(){})};window.doPause=function(){P.pause().catch(function(){})};
          window.doSeek=function(t){P.setCurrentTime(t).catch(function(){})};
          P.ready().then(function(){S.r=true;if($start>0)return P.setCurrentTime($start)}).catch(function(){S.e=-2});
          P.on('timeupdate',function(d){S.t=d.seconds;S.d=d.duration});
          P.on('play',function(){S.p=true});P.on('pause',function(){S.p=false});P.on('ended',function(){S.p=false});
          P.on('error',function(){S.e=-3});};
        document.head.appendChild(s);
        </script>
        """
    } else {
        val id = JSONObject.quote(videoId.orEmpty())
        """
        <div id="v"></div>
        <script>$shared
        function onYouTubeIframeAPIReady(){P=new YT.Player('v',{videoId:$id,
          playerVars:{autoplay:1,start:$start,rel:0,modestbranding:1,controls:1,fs:1,playsinline:1,iv_load_policy:3,origin:'https://itc-academy.uz'},
          events:{onReady:function(){S.r=true},onError:function(e){S.e=e.data}}})}
        window.read=function(){if(!P||!P.getCurrentTime)return;S.t=+P.getCurrentTime()||0;S.d=+P.getDuration()||0;S.p=P.getPlayerState()===1};
        window.doPlay=function(){if(P&&P.playVideo)P.playVideo()};window.doPause=function(){if(P&&P.pauseVideo)P.pauseVideo()};
        window.doSeek=function(t){if(P&&P.seekTo)P.seekTo(t,true)};
        var s=document.createElement('script');s.src='https://www.youtube.com/iframe_api';s.onerror=function(){S.e=-1};document.head.appendChild(s);
        </script>
        """
    }
    return """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
        <style>html,body{margin:0;height:100%;background:#000;overflow:hidden}#v{position:absolute;inset:0;width:100%;height:100%;border:0}</style></head><body>$body</body></html>"""
}

/** Ko'rish hisobi: ilova o'zi yozadi, server tasdiqlaydi. Saytdagi VideoTimer bilan bir xil qoida. */
private class WatchTracker(private val lessonId: Int, c: JSONObject) {
    var server by mutableStateOf(jsonSegments(c.optJSONArray("watched_segments")))
    var pending by mutableStateOf(emptyList<Seg>())
    var required by mutableStateOf(c.optDouble("required_seconds", 0.0))
    var duration by mutableStateOf(c.optDouble("duration", 0.0))
    var canComplete by mutableStateOf(c.optBoolean("can_complete"))
    var quizPending by mutableIntStateOf(c.optInt("quiz_pending"))
    var playing by mutableStateOf(false)
    var failures by mutableIntStateOf(0)
    var presenceToken by mutableStateOf<String?>(null)
    var coinAmount by mutableIntStateOf(c.optInt("coin_amount"))

    private var presenceAnswer = ""
    private var lastTime: Double? = null
    private var lastWall = 0L
    private var lastKnown by mutableStateOf(c.optDouble("resume_at", 0.0))
    private var lastSync = 0L
    private var syncing = false

    val watched: Double get() = Segments.total(Segments.union(server, pending), duration)

    fun answerPresence() {
        presenceAnswer = presenceToken.orEmpty()
        presenceToken = null
    }

    /** Bir o'qish. Yozish faqat ilova oldinda, video o'ynayotgan va oyna ochiq bo'lmaganda. */
    fun onSample(s: PlayerState, canRecord: Boolean): Boolean {
        lastKnown = s.time
        if (duration <= 0 && s.duration >= 2) duration = s.duration
        val now = SystemClock.elapsedRealtime()
        val record = s.playing && canRecord
        val prev = lastTime
        if (record && prev != null) {
            val dPos = s.time - prev
            val dWall = (now - lastWall) / 1000.0
            if (Segments.isRealPlayback(dPos, dWall)) pending = Segments.union(pending, listOf(Seg(prev, s.time)))
        }
        lastTime = if (record) s.time else null
        lastWall = now
        val stopped = playing && !s.playing
        playing = s.playing
        return stopped
    }

    fun forgetSample() { lastTime = null }

    /** Birinchi ko'rilmagan joy. Faqat o'quvchi undan o'tib ketgan bo'lsa qaytariladi. */
    fun gapTarget(): Double? {
        if (canComplete) return null
        val all = Segments.union(server, pending)
        val target = if (all.isNotEmpty() && all[0].start <= 1) all[0].end else 0.0
        if (duration > 0 && target >= duration - 1) return null
        return target.takeIf { lastKnown > it + 3 }
    }

    fun shouldSync(): Boolean =
        pending.isNotEmpty() || presenceAnswer.isNotEmpty() ||
            (playing && SystemClock.elapsedRealtime() - lastSync > 60_000)

    suspend fun sync() {
        if (syncing) return
        syncing = true
        lastSync = SystemClock.elapsedRealtime()
        val sending = pending
        val answer = presenceAnswer
        try {
            val body = JSONObject()
                .put("segments", JSONArray(sending.map { JSONArray().put(round3(it.start)).put(round3(it.end)) }))
                .put("position", lastKnown)
                .put("presence_token", answer)
            val r = Api.post("/api/v1/app/lessons/$lessonId/video/beat/", body)
            failures = 0
            server = jsonSegments(r.optJSONArray("watched_segments"))
            var rest = Segments.subtract(pending, sending)
            if (r.optBoolean("budget_limited")) rest = Segments.union(rest, Segments.subtract(sending, server))
            pending = Segments.subtract(rest, server)
            if (answer.isNotEmpty() && presenceAnswer == answer) presenceAnswer = ""
            if (r.optDouble("required_seconds", 0.0) > 0) required = r.optDouble("required_seconds")
            if (r.optDouble("duration", 0.0) > 0) duration = r.optDouble("duration")
            quizPending = r.optInt("quiz_pending")
            canComplete = r.optBoolean("can_complete")
            val token = r.optJSONObject("presence")?.strOrNull("token")
            if (token != null && !canComplete && token != presenceAnswer) presenceToken = token
        } catch (e: ApiError) {
            failures++
        } finally {
            syncing = false
        }
    }

    private fun round3(v: Double) = Math.round(v * 1000) / 1000.0
}

@Composable
fun VideoLessonContent(data: JSONObject, content: JSONObject?) {
    val id = data.int("id")
    val provider = content?.strOrNull("provider")
    val videoId = content?.strOrNull("video_id")
    val embed = content?.strOrNull("embed_url")
    val usable = content != null && (
        (provider == "youtube" && videoId != null && Regex("[A-Za-z0-9_-]{11}").matches(videoId)) ||
            (provider == "vimeo" && embed != null && Uri.parse(embed).host == "player.vimeo.com")
        )
    if (!usable) {
        Column(Modifier.statusBarsPadding().padding(16.dp)) {
            BackHeader(data.str("title"), onBack = { AppState.back() })
            EmptyState(Icons.Rounded.PlayCircle, "Bu dars uçun video qöşilmagan")
        }
        return
    }
    PlayerScreen(data, content!!, provider!!, videoId, embed, id)
}

@Composable
private fun PlayerScreen(data: JSONObject, c: JSONObject, provider: String, videoId: String?, embed: String?, lessonId: Int) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val view = LocalView.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val frame = remember { PlayerFrame(ctx, provider, videoId, embed, c.optDouble("resume_at", 0.0)) }
    val tracker = remember { WatchTracker(lessonId, c) }
    var watched by remember { mutableStateOf(c.optBoolean("watched")) }
    var resumed by remember { mutableStateOf(true) }
    var error by remember { mutableIntStateOf(0) }
    var ready by remember { mutableStateOf(false) }
    var completing by remember { mutableStateOf(false) }
    var celebrate by remember { mutableStateOf<JSONObject?>(null) }

    val quizzes = remember {
        val arr = c.optJSONArray("quizzes")
        mutableStateListOf<JSONObject>().apply { for (i in 0 until (arr?.length() ?: 0)) add(arr!!.getJSONObject(i)) }
    }
    var quiz by remember { mutableStateOf<JSONObject?>(null) }
    var quizResolved by remember { mutableStateOf(false) }

    // Ilova orqaga o'tsa video va hisob to'xtaydi
    DisposableEffect(lifecycle) {
        val obs = LifecycleEventObserver { _, e ->
            when (e) {
                Lifecycle.Event.ON_PAUSE -> {
                    resumed = false
                    tracker.forgetSample()
                    frame.web.onPause()
                    if (!watched) scope.launch { tracker.sync() }
                }
                Lifecycle.Event.ON_RESUME -> { resumed = true; frame.web.onResume() }
                else -> {}
            }
        }
        lifecycle.addObserver(obs)
        onDispose {
            lifecycle.removeObserver(obs)
            // Savol ochiq qolib chiqib ketilsa, saytdagidek javob berilmagan hisoblanadi
            val open = quiz
            if (open != null && !quizResolved) AppScope.launch { submitTimeout(open) }
            if (!watched && tracker.pending.isNotEmpty()) AppScope.launch { tracker.sync() }
            frame.destroy()
        }
    }

    // Sampler: soniyada bir marta
    LaunchedEffect(watched) {
        while (true) {
            delay(SAMPLE_MS)
            val s = frame.read() ?: continue
            ready = s.ready
            error = s.error
            view.keepScreenOn = s.playing && resumed
            if (watched) continue
            val modal = tracker.presenceToken != null || quiz != null
            val stopped = tracker.onSample(s, resumed && !modal)
            if (stopped) tracker.sync()
            if (quiz == null && tracker.presenceToken == null) {
                val due = quizzes.firstOrNull { !it.optBoolean("answered") && s.time >= it.int("trigger_second") }
                if (due != null) {
                    frame.pause()
                    frame.exitFullscreen()
                    quizResolved = false
                    quiz = due
                }
            }
        }
    }
    // Sinxron: 10 soniyada bir marta
    LaunchedEffect(watched) {
        while (!watched) {
            delay(SYNC_MS)
            if (tracker.shouldSync()) tracker.sync()
        }
    }
    // Talab bajarilganda tasdiq tezroq keladi
    val remaining = (tracker.required - tracker.watched).coerceAtLeast(0.0)
    LaunchedEffect(remaining <= 0.5 && tracker.required > 0, tracker.canComplete) {
        while (remaining <= 0.5 && tracker.required > 0 && !tracker.canComplete && !watched) {
            tracker.sync()
            delay(2500)
        }
    }
    LaunchedEffect(tracker.presenceToken) {
        if (tracker.presenceToken != null) { frame.pause(); frame.exitFullscreen(); tracker.forgetSample() }
    }

    // To'liq ekran
    val activity = ctx as? Activity
    val full = frame.custom
    LaunchedEffect(full != null) {
        val w = activity?.window ?: return@LaunchedEffect
        val ctl = WindowCompat.getInsetsController(w, view)
        if (full != null) {
            activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
            ctl.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            ctl.hide(WindowInsetsCompat.Type.systemBars())
        } else {
            activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            ctl.show(WindowInsetsCompat.Type.systemBars())
        }
    }
    DisposableEffect(Unit) {
        onDispose {
            view.keepScreenOn = false
            activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            activity?.window?.let { WindowCompat.getInsetsController(it, view).show(WindowInsetsCompat.Type.systemBars()) }
        }
    }
    BackHandler(full != null) { frame.exitFullscreen() }

    fun complete() {
        completing = true
        scope.launch {
            try {
                if (tracker.pending.isNotEmpty()) tracker.sync()
                val r = Api.post("/api/v1/app/lessons/$lessonId/video/complete/")
                if (r.optBoolean("success")) {
                    watched = true
                    celebrate = r
                    AppState.refreshUser()
                } else Toasts.show(r.str("error").ifEmpty { t("Kutilmagan xatolik") }, "err")
            } catch (e: ApiError) {
                e.data?.optInt("quiz_pending")?.let { tracker.quizPending = it }
                Toasts.show(e.message ?: "", "err")
            }
            completing = false
        }
    }

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().statusBarsPadding()) {
            Box(Modifier.padding(start = 16.dp, end = 16.dp, top = 10.dp, bottom = 10.dp)) {
                BackHeader(data.str("title"), data.optJSONObject("course")?.str("name"), onBack = { AppState.back() })
            }
            Box(
                Modifier.padding(horizontal = 12.dp).fillMaxWidth().aspectRatio(16f / 9f).clip(RoundedCornerShape(20.dp))
                    .background(Color.Black).border(1.dp, pal.border, RoundedCornerShape(20.dp)),
            ) {
                AndroidView({ frame.web }, Modifier.fillMaxSize())
                if (!ready && error == 0) Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Spinner(30.dp, Color.White) }
                if (error != 0) PlayerError(provider, videoId, embed)
            }
            Column(
                Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(start = 16.dp, end = 16.dp, top = 14.dp, bottom = 40.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                if (watched) WatchedCard()
                else TimerCard(tracker, resumed, remaining, completing, onSeekGap = { target ->
                    tracker.forgetSample()
                    frame.seek(kotlin.math.max(0.0, target - 1))
                    frame.play()
                }) { complete() }
                LessonNextButton(data, enabled = watched)
                c.strOrNull("article")?.let { ArticleCard(it) }
            }
        }

        val presence = tracker.presenceToken
        if (presence != null) Overlay {
            Tinted(pal.a1.copy(alpha = .16f), Modifier.size(62.dp), CircleShape) { Icon(Icons.Rounded.Visibility, null, Modifier.size(30.dp), pal.a1) }
            Spacer(Modifier.height(12.dp))
            Txt("Şu yerdamisiz?", size = 20.sp, weight = FontWeight.Bold)
            Muted("Video töxtatildi. Körilgan vaqtingiz saqlangan — tugmani bosib davom eting.", Modifier.padding(top = 6.dp, bottom = 16.dp), 14.sp)
            Btn("Ha, davom etaman", Modifier.fillMaxWidth(), BtnKind.Primary, Icons.Rounded.PlayArrow) {
                tracker.answerPresence()
                frame.play()
                scope.launch { tracker.sync() }
            }
        }

        val q = quiz
        if (q != null) key(q.int("id")) {
            QuizOverlay(q, onResolved = {
                quizResolved = true
                q.put("answered", true)
                tracker.forgetSample()
            }) {
                quiz = null
                frame.play()
                scope.launch { tracker.sync(); AppState.refreshUser() }
            }
        }

        val done = celebrate
        if (done != null) Overlay {
            Txt("🎉", size = 44.sp, translate = false)
            Txt("Ajoyib!", size = 22.sp, weight = FontWeight.Bold, modifier = Modifier.padding(top = 6.dp))
            Muted("Video darsni muvaffaqiyatli tugatdingiz", Modifier.padding(top = 4.dp, bottom = 12.dp), 14.sp)
            val coin = done.int("coin_amount")
            if (coin > 0) Row(verticalAlignment = Alignment.CenterVertically) {
                CoinDot(22.dp); Spacer(Modifier.width(6.dp))
                Txt("+${num(coin)} coin", size = 18.sp, weight = FontWeight.Bold, color = pal.amber, translate = false)
            }
            Spacer(Modifier.height(16.dp))
            Btn("Davom etiş", Modifier.fillMaxWidth(), BtnKind.Primary) { celebrate = null }
        }

        if (full != null) AndroidView({ full }, Modifier.fillMaxSize().background(Color.Black))
    }
}

@Composable
private fun PlayerError(provider: String, videoId: String?, embed: String?) {
    val ctx = LocalContext.current
    Column(Modifier.fillMaxSize().background(Color(0xE6000000)).padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Icon(Icons.Rounded.ErrorOutline, null, Modifier.size(30.dp), Color.White)
        Txt("Video bu oynada oçilmadi", color = Color.White, weight = FontWeight.SemiBold, modifier = Modifier.padding(top = 6.dp))
        Txt("Taşqarida körilgan vaqt hisobga olinmaydi.", color = Color.White.copy(alpha = .75f), size = 12.5.sp, align = TextAlign.Center, modifier = Modifier.padding(top = 2.dp, bottom = 10.dp))
        Btn(if (provider == "vimeo") "Vimeo'da oçiş" else "YouTube'da oçiş", small = true, icon = Icons.Rounded.OpenInNew) {
            openBrowser(ctx, if (provider == "vimeo") embed.orEmpty() else "https://www.youtube.com/watch?v=$videoId")
        }
    }
}

@Composable
private fun WatchedCard() {
    Row(Modifier.fillMaxWidth().card(fill = pal.green.copy(alpha = .13f)).padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Rounded.CheckCircle, null, Modifier.size(26.dp), pal.green); Spacer(Modifier.width(10.dp))
        Column {
            Txt("Bu dars yakunlangan", weight = FontWeight.SemiBold)
            Muted("Videoni istagan vaqtda qayta körişingiz mumkin.")
        }
    }
}

@Composable
private fun TimerCard(tr: WatchTracker, resumed: Boolean, remaining: Double, busy: Boolean, onSeekGap: (Double) -> Unit, onComplete: () -> Unit) {
    val p = pal
    val watched = tr.watched
    val fraction = if (tr.canComplete) 1f else if (tr.required > 0) (watched / tr.required).toFloat().coerceIn(0f, 1f) else 0f
    val anim by animateFloatAsState(fraction, spring(.9f, Spring.StiffnessLow), label = "watch")
    val color = when { tr.canComplete -> p.green; tr.playing && resumed -> p.a1; else -> p.amber }
    val status = when {
        tr.canComplete -> "Endi \"Kördim\" tugmasini bosişingiz mumkin"
        tr.required <= 0 -> "Video davomiyligi aniqlanmoqda…"
        remaining <= 0.5 && tr.quizPending > 0 -> "Video içidagi ${tr.quizPending} ta savolga javob bering"
        remaining <= 0.5 -> "Köriş vaqti serverda tasdiqlanmoqda…"
        !resumed -> "Ilovadan çiqdingiz — taymer töxtadi"
        tr.playing && tr.failures >= 2 -> "Internet sekin — progress saqlanib turibdi, körişda davom eting"
        tr.playing -> "Video ijro etilmoqda…"
        watched == 0.0 -> "Videoning kamida 90% ini köring"
        else -> "Töxtatildi — davom ettiriş uçun videoni ijro eting"
    }
    Column(Modifier.fillMaxWidth().card().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(78.dp), contentAlignment = Alignment.Center) {
                val track = p.surface3
                Canvas(Modifier.fillMaxSize()) {
                    val st = Stroke(size.width * .09f, cap = StrokeCap.Round)
                    drawArc(track, 0f, 360f, false, style = st)
                    drawArc(color, -90f, 360f * anim, false, style = st)
                }
                if (tr.canComplete) Icon(Icons.Rounded.Check, null, Modifier.size(30.dp), p.green)
                else Txt(if (tr.required > 0) clock(kotlin.math.ceil(remaining)) else "—:—", size = 15.sp, weight = FontWeight.Bold, translate = false)
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Txt(if (tr.canComplete) "Tayyor!" else "Qolgan vaqt", weight = FontWeight.SemiBold, size = 15.sp)
                Muted(status, Modifier.padding(top = 2.dp))
                Row(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Muted("${t("Körildi")}: ${clock(watched)}", translate = false, size = 12.sp)
                    if (tr.duration > 0) Muted("${t("Jami")}: ${clock(tr.duration)}", translate = false, size = 12.sp)
                }
            }
        }
        val gap = tr.gapTarget()
        if (gap != null) {
            Spacer(Modifier.height(12.dp))
            Btn("Körilmagan joyga ötiş (${clock(gap)})", Modifier.fillMaxWidth(), icon = Icons.Rounded.History, small = true) { onSeekGap(gap) }
        }
        if (tr.canComplete) {
            Spacer(Modifier.height(14.dp))
            Btn("Kördim  +${num(tr.coinAmount)} coin", Modifier.fillMaxWidth(), BtnKind.Primary, Icons.Rounded.CheckCircle, busy = busy, onClick = onComplete)
        }
    }
}

@Composable
private fun ArticleCard(html: String) {
    var open by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().card()) {
        Row(Modifier.fillMaxWidth().press(scale = .99f) { open = !open }.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Rounded.Article, null, Modifier.size(20.dp), pal.a1); Spacer(Modifier.width(10.dp))
            Txt("Dars maqolasi", Modifier.weight(1f), weight = FontWeight.SemiBold)
            Icon(if (open) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore, null, Modifier.size(22.dp), pal.muted)
        }
        if (open) RichText(html, Modifier.padding(start = 14.dp, end = 14.dp, bottom = 14.dp))
    }
}

/** Yopilmaydigan oyna: tashqariga bosish va orqaga tugmasi ishlamaydi. */
@Composable
private fun Overlay(content: @Composable ColumnScope.() -> Unit) {
    BackHandler { }
    Box(
        Modifier.fillMaxSize().background(Color(0xD9050412)).clickable(remember { MutableInteractionSource() }, null) { },
        contentAlignment = Alignment.Center,
    ) {
        Column(
            Modifier.padding(18.dp).fillMaxWidth().heightIn(max = 620.dp).clip(RoundedCornerShape(28.dp))
                // Video oynasi ustida xiralashtirish ishlamaydi: matn o'qilishi uchun panel to'q
                .background(if (pal.dark) Color(0xFF1A1A28) else Color.White).border(1.dp, pal.border, RoundedCornerShape(28.dp))
                .verticalScroll(rememberScrollState()).padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            content = content,
        )
    }
}

private suspend fun submitTimeout(q: JSONObject): JSONObject? {
    repeat(3) { i ->
        try {
            return Api.post(
                "/api/v1/app/video-quiz/submit/",
                JSONObject().put("quiz_id", q.int("id")).put("selected", JSONObject.NULL).put("timeout", true),
            )
        } catch (e: ApiError) {
            if (e.status != 0) return e.data
            delay(800L * (i + 1))
        }
    }
    return null
}

@Composable
private fun QuizOverlay(q: JSONObject, onResolved: () -> Unit, onContinue: () -> Unit) {
    val scope = rememberCoroutineScope()
    val opened = remember { SystemClock.elapsedRealtime() }
    var selected by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<JSONObject?>(null) }
    var timedOut by remember { mutableStateOf(false) }
    var secondsLeft by remember { mutableIntStateOf(QUIZ_ANSWER_SECONDS) }
    var autoLeft by remember { mutableIntStateOf(QUIZ_AUTO_CONTINUE_SECONDS) }
    val finished = result != null || timedOut

    LaunchedEffect(Unit) {
        while (result == null) {
            secondsLeft = (QUIZ_ANSWER_SECONDS - (SystemClock.elapsedRealtime() - opened) / 1000).toInt().coerceAtLeast(0)
            if (secondsLeft == 0 && !busy) {
                timedOut = true
                onResolved()
                result = submitTimeout(q) ?: JSONObject().put("error", t("Internet aloqasi yöq"))
                return@LaunchedEffect
            }
            delay(250)
        }
    }
    LaunchedEffect(result) {
        if (result == null) return@LaunchedEffect
        while (autoLeft > 0) { delay(1000); autoLeft-- }
        onContinue()
    }

    val r = result
    val correct = r?.strOrNull("correct_option")
    val options = q.optJSONObject("options") ?: JSONObject()
    Overlay {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Txt("Video savoli", Modifier.weight(1f), weight = FontWeight.SemiBold, color = pal.a1)
            if (!finished) Txt("$secondsLeft s", weight = FontWeight.Bold, color = if (secondsLeft <= 10) pal.red else pal.text2, translate = false)
        }
        Spacer(Modifier.height(8.dp))
        ProgressBar(if (finished) 1f else secondsLeft / QUIZ_ANSWER_SECONDS.toFloat(), color = if (secondsLeft <= 10) pal.red else pal.a1)
        Spacer(Modifier.height(12.dp))
        Txt(q.str("question"), Modifier.fillMaxWidth(), 16.sp, FontWeight.SemiBold, translate = false)
        q.strOrNull("description")?.let { Muted(it, Modifier.fillMaxWidth().padding(top = 4.dp), translate = false) }
        Spacer(Modifier.height(12.dp))
        listOf("A", "B", "C", "D").forEach { letter ->
            val on = selected == letter
            val isRight = correct == letter
            val isWrong = r != null && on && !r.optBoolean("correct")
            val fill = when { isRight -> pal.green.copy(alpha = .18f); isWrong -> pal.red.copy(alpha = .16f); on -> pal.a1.copy(alpha = .16f); else -> pal.surface }
            val edge = when { isRight -> pal.green; isWrong -> pal.red; on -> pal.a1; else -> pal.border }
            Row(
                Modifier.padding(bottom = 8.dp).fillMaxWidth().press(enabled = !finished && !busy, scale = .98f) { selected = letter }
                    .clip(RoundedCornerShape(14.dp)).background(fill).border(1.dp, edge, RoundedCornerShape(14.dp)).padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Tinted(edge.copy(alpha = .2f), Modifier.size(28.dp), CircleShape) { Txt(letter, size = 12.5.sp, weight = FontWeight.Bold, translate = false) }
                Spacer(Modifier.width(10.dp))
                Txt(options.str(letter), Modifier.weight(1f), translate = false)
            }
        }
        if (!finished) {
            Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Txt("+${q.int("reward_coin")} coin", size = 12.5.sp, color = pal.green, translate = false)
                Txt("-${q.int("penalty_coin")} coin", size = 12.5.sp, color = pal.red, translate = false)
            }
            Btn("Javobni yuboriş", Modifier.fillMaxWidth(), BtnKind.Primary, Icons.Rounded.Send, enabled = selected != null, busy = busy) {
                busy = true
                scope.launch {
                    val ms = SystemClock.elapsedRealtime() - opened
                    try {
                        result = Api.post(
                            "/api/v1/app/video-quiz/submit/",
                            JSONObject().put("quiz_id", q.int("id")).put("selected", selected).put("answer_ms", ms),
                        )
                        onResolved()
                    } catch (e: ApiError) {
                        if (e.status == 0) {
                            Toasts.show(e.message ?: "", "err")
                            busy = false
                        } else {
                            // Masalan, allaqachon javob berilgan: savol qayta to'sib turmasin
                            onResolved()
                            Toasts.show(e.message ?: "", "info")
                            onContinue()
                        }
                    }
                }
            }
        } else if (r != null) {
            val title = when {
                r.has("error") -> r.str("error")
                timedOut -> "Vaqt tugadi"
                r.optBoolean("correct") -> "Töğri javob!"
                else -> "Notöğri javob"
            }
            Txt(title, size = 17.sp, weight = FontWeight.Bold, color = if (r.optBoolean("correct")) pal.green else pal.red, modifier = Modifier.padding(top = 4.dp))
            if (r.has("coins_change")) {
                val change = r.int("coins_change")
                Txt("${if (change > 0) "+" else ""}$change coin · ${t("balans")}: ${num(r.int("balance"))}", weight = FontWeight.SemiBold, translate = false, modifier = Modifier.padding(top = 2.dp))
            }
            r.strOrNull("explanation")?.let { Muted(it, Modifier.fillMaxWidth().padding(top = 8.dp), 13.5.sp, translate = false) }
            Spacer(Modifier.height(12.dp))
            Btn("Davom etiş ($autoLeft)", Modifier.fillMaxWidth(), BtnKind.Primary, Icons.Rounded.PlayArrow, onClick = onContinue)
        } else {
            Spinner(24.dp)
        }
    }
}
