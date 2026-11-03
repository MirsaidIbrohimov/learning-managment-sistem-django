package uz.itcacademy.parent

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
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
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.hazeSource
import kotlinx.coroutines.launch
import org.json.JSONObject
import uz.itcacademy.parent.screens.*
import uz.itcacademy.parent.ui.*
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

sealed class Route {
    data object Children : Route()
    data object Achievements : Route()
    data object Books : Route()
    data object Messages : Route()
    data object Notifications : Route()
    data object Profile : Route()
    data object EditProfile : Route()
    data object Password : Route()
    data object SettingsPage : Route()
    data object Security : Route()
    data object Help : Route()
}

data class TabDef(val id: String, val label: String, val icon: ImageVector)

val TABS = listOf(
    TabDef("home", "Bosh sahifa", Icons.Rounded.Home),
    TabDef("study", "Öqiş", Icons.Rounded.MenuBook),
    TabDef("attendance", "Davomat", Icons.Rounded.EventAvailable),
    TabDef("payments", "Tölov", Icons.Rounded.AccountBalanceWallet),
    TabDef("more", "Yana", Icons.Rounded.GridView),
)

/** Ilova holati: ota-ona, farzandlar, tanlangan farzand va navigatsiya. */
object AppState {
    var me by mutableStateOf<JSONObject?>(null)
    var children by mutableStateOf<List<JSONObject>>(emptyList())
    var childId by mutableIntStateOf(0)
    val stack = mutableStateListOf<Route>()
    var tab by mutableStateOf("home")
    var studyTab by mutableIntStateOf(0)
    var forward by mutableStateOf(true)
    var unreadNotif by mutableIntStateOf(0)
    var unreadReplies by mutableIntStateOf(0)
    var pendingTarget: Pair<String, Int>? = null

    val child: JSONObject? get() = children.firstOrNull { it.int("id") == childId } ?: children.firstOrNull()
    val parent: JSONObject? get() = me?.obj("parent")

    fun selectChild(id: Int) {
        if (id == childId) return
        childId = id
        Settings.childId = id
    }

    fun open(r: Route) { forward = true; stack += r }
    fun back(): Boolean {
        if (stack.isEmpty()) return false
        forward = false
        stack.removeAt(stack.lastIndex)
        return true
    }
    fun switchTab(name: String) {
        forward = TABS.indexOfFirst { it.id == name } > TABS.indexOfFirst { it.id == tab }
        stack.clear()
        tab = name
    }

    /** Bildirishnomadan kelgan manzilga o'tish. */
    fun go(target: String?, child: Int = 0) {
        if (child != 0 && children.any { it.int("id") == child }) selectChild(child)
        when (target) {
            "tests" -> { studyTab = 2; switchTab("study") }
            "homework" -> { studyTab = 1; switchTab("study") }
            "lessons" -> { studyTab = 0; switchTab("study") }
            "attendance" -> switchTab("attendance")
            "payments" -> switchTab("payments")
            "messages" -> { switchTab("more"); open(Route.Messages) }
            "achievements" -> { switchTab("more"); open(Route.Achievements) }
            "books" -> { switchTab("more"); open(Route.Books) }
            "notifications" -> { switchTab("home"); open(Route.Notifications) }
        }
    }

    suspend fun refresh() {
        val r = Api.get("me/", fresh = true)
        me = r
        children = r.list("children")
        unreadReplies = r.int("unread_replies")
        if (children.none { it.int("id") == childId }) childId = children.firstOrNull()?.int("id") ?: 0
    }

    suspend fun refreshBadge(ctx: Context) {
        try {
            val since = isoUtc(System.currentTimeMillis() - 13L * 86_400_000L)
            val events = Api.get("notifications/", mapOf("since" to since)).list("events")
            val viewed = ctx.getSharedPreferences("itcp_notify", Context.MODE_PRIVATE).getLong("viewedAt", 0L)
            unreadNotif = events.count { (parseDate(it.str("at"))?.time ?: 0L) > viewed }
        } catch (_: ApiError) { }
    }

    fun markNotifViewed(ctx: Context) {
        ctx.getSharedPreferences("itcp_notify", Context.MODE_PRIVATE).edit().putLong("viewedAt", System.currentTimeMillis()).apply()
        unreadNotif = 0
    }

    fun reset() {
        me = null
        children = emptyList()
        childId = 0
        stack.clear()
        tab = "home"
        studyTab = 0
        unreadNotif = 0
        unreadReplies = 0
    }
}

fun isoUtc(ms: Long): String =
    SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }.format(Date(ms))

class MainActivity : FragmentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        // Ekran rasmi, yozib olish va "so'nggi ilovalar" oynasida farzand ma'lumotlari ko'rinmaydi
        // (faqat debug build'da sinov skrinshotlari uchun o'chiq)
        if (!BuildConfig.DEBUG) window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        Secure.init(this)
        Settings.init(this)
        Notify.createChannels(this)
        AppState.childId = Settings.childId
        takeTarget(intent)
        setContent { Root(this) }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        takeTarget(intent)
    }

    private fun takeTarget(i: Intent?) {
        val target = i?.getStringExtra("target") ?: return
        AppState.pendingTarget = target to i.getIntExtra("child_id", 0)
        i.removeExtra("target")
        Session.deepLink++
    }
}

/** Kirish bosqichlari. */
object Session {
    var phase by mutableStateOf("starting")
    var deepLink by mutableIntStateOf(0)
}

/** Hisobdan chiqish: serverdagi token bekor qilinadi, qurilmada hech narsa qolmaydi. */
suspend fun signOut(ctx: Context, remote: Boolean = true) {
    if (remote && Api.token != null) runCatching { Api.post("logout/") }
    Api.clearCache()
    Secure.prefs.edit().clear().apply()   // token, PIN xeshi, ism
    Settings.clearAccount()
    Notify.cancel(ctx)
    AppState.reset()
    Session.phase = "login"
}

@Composable
fun Root(activity: FragmentActivity) {
    val ctx = LocalContext.current
    val dark = when (Settings.theme) { "light" -> false; "system" -> isSystemInDarkTheme(); else -> true }
    val scope = rememberCoroutineScope()
    val haze = remember { HazeState() }
    val phase = Session.phase

    fun load() {
        scope.launch {
            try {
                AppState.refresh()
                Session.phase = "app"
                Notify.schedule(ctx)
                launch { runCatching { Notify.sync(ctx) }; AppState.refreshBadge(ctx) }
            } catch (e: ApiError) {
                if (e.status == 0 || e.status >= 500) Session.phase = "offline"
            }
        }
    }

    LaunchedEffect(Unit) {
        Api.onUnauthorized = {
            scope.launch {
                if (Session.phase != "login") Toasts.show("Sessiya tugadi. Iltimos, qaytadan kiring", "info")
                signOut(ctx, remote = false)
            }
        }
        Session.phase = when {
            Api.token == null -> "login"
            !Pin.isSet -> "setpin"
            else -> "lock"
        }
    }

    // Fondan qaytilganda PIN qayta so'raladi
    DisposableEffect(Unit) {
        val obs = object : DefaultLifecycleObserver {
            override fun onStop(owner: LifecycleOwner) { AutoLock.onHidden() }
            override fun onStart(owner: LifecycleOwner) {
                if ((Session.phase == "app" || Session.phase == "offline") && Pin.isSet && AutoLock.shouldLock()) {
                    Sheets.stack.clear()
                    Session.phase = "lock"
                } else if (Session.phase == "app") {
                    scope.launch { runCatching { Notify.sync(ctx) }; AppState.refreshBadge(ctx) }
                }
                AutoLock.reset()
            }
        }
        val lc = ProcessLifecycleOwner.get().lifecycle
        lc.addObserver(obs)
        onDispose { lc.removeObserver(obs) }
    }

    LaunchedEffect(Session.deepLink, phase) {
        if (phase == "app") AppState.pendingTarget?.let { (t, c) -> AppState.pendingTarget = null; AppState.go(t, c) }
    }

    val view = androidx.compose.ui.platform.LocalView.current
    SideEffect {
        androidx.core.view.WindowCompat.getInsetsController(activity.window, view).apply {
            isAppearanceLightStatusBars = !dark
            isAppearanceLightNavigationBars = !dark
        }
    }
    val density = LocalDensity.current
    val scaled = remember(density, Settings.largeText) {
        Density(density.density, density.fontScale * if (Settings.largeText) 1.15f else 1f)
    }
    CompositionLocalProvider(LocalDensity provides scaled) {
        GlassTheme(dark) {
            CompositionLocalProvider(LocalHaze provides haze) {
                Box(Modifier.fillMaxSize()) {
                    Box(Modifier.fillMaxSize().hazeSource(haze)) {
                        Wallpaper()
                        AnimatedContent(
                            phase,
                            transitionSpec = {
                                if (!motionOn) fadeIn(tween(0)) togetherWith fadeOut(tween(0))
                                else (fadeIn(tween(320)) + scaleIn(initialScale = .96f, animationSpec = tween(320))) togetherWith
                                    (fadeOut(tween(200)) + scaleOut(targetScale = 1.03f, animationSpec = tween(200)))
                            },
                            label = "phase",
                        ) { ph ->
                            when (ph) {
                                "login" -> LoginScreen(onDone = { Session.phase = "setpin" })
                                "setpin" -> SetPinScreen(onDone = { load() })
                                "lock" -> LockScreen(activity, onUnlock = { load() })
                                "app" -> Shell()
                                "offline" -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                                    EmptyState(Icons.Rounded.WifiOff, "Internet aloqasi yöq", "ITC Academy serveriga ulanib bölmadi. Internetni tekşirib, qayta urinib köring.") {
                                        Btn("Qayta urinish", kind = BtnKind.Primary, icon = Icons.Rounded.Refresh) { load() }
                                    }
                                }
                                else -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Spinner(30.dp) }
                            }
                        }
                    }
                    Box(
                        Modifier.fillMaxWidth().windowInsetsTopHeight(WindowInsets.statusBars)
                            .background(Brush.verticalGradient(listOf(pal.bg.copy(alpha = .86f), pal.bg.copy(alpha = .35f)))),
                    )
                    val keyboard = WindowInsets.ime.getBottom(LocalDensity.current) > 0
                    if (phase == "app" && AppState.stack.isEmpty() && !keyboard) BottomBar(Modifier.align(Alignment.BottomCenter))
                    SheetHost()
                    if (phase == "app" && !Settings.tourDone) TourOverlay(onDone = {
                        Settings.tourDone = true
                        askNotifications(activity)
                    })
                    ToastHost()
                }
            }
        }
    }
}

/** Android 13+: qo'llanmadan keyin bir marta ruxsat so'raladi. */
fun askNotifications(activity: FragmentActivity) {
    if (Settings.askedNotify || android.os.Build.VERSION.SDK_INT < 33) return
    Settings.askedNotify = true
    activity.requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 7)
}

@Composable
fun Shell() {
    val stack = AppState.stack
    val top: Any = stack.lastOrNull() ?: AppState.tab
    BackHandler(stack.isNotEmpty() || AppState.tab != "home") {
        if (!AppState.back()) AppState.switchTab("home")
    }
    AnimatedContent(
        top,
        transitionSpec = {
            if (!motionOn) fadeIn(tween(0)) togetherWith fadeOut(tween(0))
            else {
                val dir = if (AppState.forward) 1 else -1
                (slideInHorizontally(spring(.86f, Spring.StiffnessMediumLow)) { it / 4 * dir } + fadeIn(tween(200)) + scaleIn(initialScale = .985f)) togetherWith
                    (slideOutHorizontally(tween(220)) { -it / 8 * dir } + fadeOut(tween(160)))
            }
        },
        label = "nav",
    ) { r ->
        when (r) {
            "study" -> StudyScreen()
            "attendance" -> AttendanceScreen()
            "payments" -> PaymentsScreen()
            "more" -> MoreScreen()
            Route.Children -> ChildrenScreen()
            Route.Achievements -> AchievementsScreen()
            Route.Books -> BooksScreen()
            Route.Messages -> MessagesScreen()
            Route.Notifications -> NotificationsScreen()
            Route.Profile -> ProfileScreen()
            Route.EditProfile -> EditProfileScreen()
            Route.Password -> PasswordScreen()
            Route.SettingsPage -> SettingsScreen()
            Route.Security -> SecurityScreen()
            Route.Help -> HelpScreen()
            else -> HomeScreen()
        }
    }
}

/** Suzuvchi shisha panel: tanlangan belgi orqasida shisha sirpanadi. */
@Composable
fun BottomBar(modifier: Modifier = Modifier) {
    val p = pal
    var w by remember { mutableIntStateOf(0) }
    val density = LocalDensity.current
    val idx = TABS.indexOfFirst { it.id == AppState.tab }.coerceAtLeast(0)
    val itemW = with(density) { (w / TABS.size).toDp() }
    val x by animateDpAsState(itemW * idx, spring(.72f, Spring.StiffnessMediumLow), label = "tab")
    Box(
        modifier.navigationBarsPadding().padding(start = 14.dp, end = 14.dp, bottom = 10.dp).fillMaxWidth().height(68.dp)
            .glassBlur(RoundedCornerShape(30.dp)).onSizeChanged { w = it.width },
    ) {
        if (w > 0) Box(
            Modifier.offset(x = x).width(itemW).fillMaxHeight().padding(5.dp).clip(RoundedCornerShape(25.dp)).background(p.surface2),
        )
        Row(Modifier.fillMaxSize()) {
            TABS.forEach { tab ->
                val on = tab.id == AppState.tab
                val sc by animateFloatAsState(if (on && motionOn) 1.14f else 1f, spring(.45f, Spring.StiffnessMedium), label = "ico")
                Column(
                    Modifier.weight(1f).fillMaxHeight().press(scale = .9f) { AppState.switchTab(tab.id) },
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    Box {
                        Icon(tab.icon, tab.label, Modifier.size(24.dp).graphicsLayer { scaleX = sc; scaleY = sc }, if (on) p.a1 else p.text2)
                        if (tab.id == "more" && AppState.unreadReplies > 0) Box(
                            Modifier.align(Alignment.TopEnd).offset(x = 4.dp, y = (-2).dp).size(9.dp).clip(CircleShape).background(p.red),
                        )
                    }
                    Spacer(Modifier.height(3.dp))
                    Txt(tab.label.substringBefore(' '), size = 10.5.sp, weight = FontWeight.Medium, color = if (on) p.text else p.muted, lines = 1)
                }
            }
        }
    }
}

/** Tizim brauzerida ochish. WebView ishlatilmaydi. */
fun openBrowser(ctx: Context, url: String) {
    runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
        .onFailure { Toasts.show("Brauzerni oçib bölmadi", "err") }
}
