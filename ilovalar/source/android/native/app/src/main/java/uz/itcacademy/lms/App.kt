package uz.itcacademy.lms

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.hazeSource
import kotlinx.coroutines.launch
import org.json.JSONObject
import uz.itcacademy.lms.screens.*
import uz.itcacademy.lms.ui.*

sealed class Route {
    data class Tab(val name: String) : Route()
    data class Course(val id: Int) : Route()
    data object Results : Route()
    data object Library : Route()
    data object Profile : Route()
    data object SettingsPage : Route()
    data class Lesson(val id: Int) : Route()
    data object MyHomework : Route()
    data object Schedule : Route()
    data object Messages : Route()
    data object Chats : Route()
    data class ChatThread(val kind: String, val id: Int, val name: String) : Route()
}

/** Ilova holati: foydalanuvchi va navigatsiya steki. */
object AppState {
    var user by mutableStateOf<JSONObject?>(null)
    val stack = mutableStateListOf<Route>()
    var tab by mutableStateOf("home")
    var forward by mutableStateOf(true)
    var shopTab by mutableStateOf("products")

    fun open(r: Route) { forward = true; stack += r }
    /** Joriy ekranni almashtiradi: "Keyingi dars"dan keyin orqaga bosilsa kurs ro'yxatiga qaytadi. */
    fun replace(r: Route) {
        forward = true
        if (stack.isNotEmpty()) stack[stack.lastIndex] = r else stack += r
    }
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

    suspend fun refreshUser(announce: Boolean = false) {
        val before = user?.int("coins")
        try {
            user = Api.get("/api/v1/profile/", fresh = true)
            val diff = (user?.int("coins") ?: 0) - (before ?: 0)
            if (before != null && diff != 0) Api.clearCache()
            if (announce && before != null && diff > 0 && Settings.coinToast) {
                Toasts.show("+${num(diff)} coin balansingizga qöşildi", "coin")
            }
        } catch (_: ApiError) { }
    }

    fun logout() {
        Api.token = null
        Api.clearCache()
        Settings.clearHistory()
        user = null
        stack.clear()
        tab = "home"
    }
}

data class TabDef(val id: String, val label: String, val icon: ImageVector)

val TABS = listOf(
    TabDef("home", "Bosh sahifa", Icons.Rounded.Home),
    TabDef("courses", "Kurslarim", Icons.Rounded.PlayCircle),
    TabDef("rating", "Reyting", Icons.Rounded.EmojiEvents),
    TabDef("shop", "Coin dökon", Icons.Rounded.ShoppingBag),
    TabDef("more", "Barça bölimlar", Icons.Rounded.GridView),
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        Settings.init(this)
        Api.init(this)
        setContent { Root() }
    }
}

@Composable
fun Root() {
    val ctx = LocalContext.current
    val dark = when (Settings.theme) { "light" -> false; "system" -> isSystemInDarkTheme(); else -> true }
    var phase by remember { mutableStateOf("starting") }
    var introDone by rememberSaveable { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val haze = remember { HazeState() }

    LaunchedEffect(Settings.lang) { I18n.load(ctx, Settings.lang) }
    fun enter() {
        scope.launch {
            phase = "starting"
            if (Api.token == null) { phase = "login"; return@launch }
            try {
                AppState.user = Api.get("/api/v1/profile/", fresh = true)
                phase = if (AppState.user?.str("role") == "student") "app" else "role"
            } catch (e: ApiError) {
                phase = if (e.status == 0) "offline" else "login"
            }
        }
    }
    LaunchedEffect(Unit) {
        Api.onUnauthorized = {
            if (AppState.user != null) Toasts.show("Sessiya tugadi. Iltimos, qaytadan kiring", "info")
            AppState.user = null
            phase = "login"
        }
        enter()
    }
    // Ilova ochilib turganda balans vaqti-vaqti bilan yangilanadi
    LaunchedEffect(phase) {
        while (phase == "app") {
            kotlinx.coroutines.delay(90_000)
            AppState.refreshUser(announce = true)
        }
    }

    val view = androidx.compose.ui.platform.LocalView.current
    SideEffect {
        val window = (view.context as? android.app.Activity)?.window ?: return@SideEffect
        androidx.core.view.WindowCompat.getInsetsController(window, view).apply {
            isAppearanceLightStatusBars = !dark
            isAppearanceLightNavigationBars = !dark
        }
    }
    GlassTheme(dark) {
        CompositionLocalProvider(LocalHaze provides haze) {
            Box(Modifier.fillMaxSize()) {
                Box(Modifier.fillMaxSize().hazeSource(haze)) {
                    Wallpaper()
                    when (phase) {
                        "login" -> LoginScreen(onDone = { enter() })
                        "app" -> Shell(onLogout = { AppState.logout(); phase = "login" })
                        "offline" -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            EmptyState(Icons.Rounded.WifiOff, "Internet aloqasi yöq", "ITC Academy serveriga ulanib bölmadi. Internetni tekşirib, qayta urinib köring.") {
                                Btn("Qayta urinish", kind = BtnKind.Primary, icon = Icons.Rounded.Refresh) { enter() }
                            }
                        }
                        "role" -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            EmptyState(Icons.Rounded.Lock, "Ilova faqat öquvçilar uçun", "Administrator, öqituvçi, ota-ona va boşqa rollar ITC Academy saytidan foydalanadi.") {
                                Btn("Boşqa hisob bilan kiriş") { AppState.logout(); phase = "login" }
                            }
                        }
                        else -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Spinner(30.dp) }
                    }
                }
                Box(
                    Modifier.fillMaxWidth().windowInsetsTopHeight(WindowInsets.statusBars)
                        .background(androidx.compose.ui.graphics.Brush.verticalGradient(listOf(pal.bg.copy(alpha = .86f), pal.bg.copy(alpha = .35f)))),
                )
                val keyboard = WindowInsets.ime.getBottom(LocalDensity.current) > 0
                if (phase == "app" && AppState.stack.isEmpty() && !keyboard) BottomBar(Modifier.align(Alignment.BottomCenter))
                SheetHost()
                ToastHost()
                if (!introDone) IntroOverlay(ready = phase != "starting", onDone = { introDone = true })
            }
        }
    }
}

@Composable
fun Shell(onLogout: () -> Unit) {
    val stack = AppState.stack
    val top: Any = stack.lastOrNull() ?: Route.Tab(AppState.tab)
    BackHandler(stack.isNotEmpty() || AppState.tab != "home") {
        if (!AppState.back()) AppState.switchTab("home")
    }
    Box(Modifier.fillMaxSize()) {
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
                is Route.Tab -> when (r.name) {
                    "courses" -> CoursesScreen()
                    "rating" -> RatingScreen()
                    "shop" -> ShopScreen()
                    "more" -> MoreScreen()
                    else -> HomeScreen()
                }
                is Route.Course -> CourseScreen(r.id)
                Route.Results -> ResultsScreen()
                Route.Library -> LibraryScreen()
                Route.Profile -> ProfileScreen()
                Route.SettingsPage -> SettingsScreen(onLogout)
                is Route.Lesson -> key(r.id) { LessonScreen(r.id) }
                Route.MyHomework -> MyHomeworkScreen()
                Route.Schedule -> ScheduleScreen()
                Route.Messages -> MessagesScreen()
                Route.Chats -> ChatsScreen()
                is Route.ChatThread -> key(r.kind, r.id) { ChatThreadScreen(r.kind, r.id, r.name) }
                else -> HomeScreen()
            }
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
        modifier.navigationBarsPadding().padding(start = 14.dp, end = 14.dp, bottom = 10.dp).fillMaxWidth().height(66.dp)
            .glassBlur(RoundedCornerShape(30.dp)).onSizeChanged { w = it.width },
    ) {
        if (w > 0) Box(
            Modifier.offset(x = x).width(itemW).fillMaxHeight().padding(5.dp).clip(RoundedCornerShape(25.dp)).background(p.surface2),
        )
        Row(Modifier.fillMaxSize()) {
            TABS.forEach { tab ->
                val on = tab.id == AppState.tab
                val sc by androidx.compose.animation.core.animateFloatAsState(
                    if (on && motionOn) 1.12f else 1f, spring(.45f, Spring.StiffnessMedium), label = "ico",
                )
                Column(
                    Modifier.weight(1f).fillMaxHeight().press(scale = .9f) { AppState.switchTab(tab.id) },
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    Icon(tab.icon, t(tab.label), Modifier.size(23.dp).graphicsLayer { scaleX = sc; scaleY = sc }, if (on) p.a1 else p.text2)
                    Spacer(Modifier.height(2.dp))
                    Txt(t(tab.label).substringBefore(' ').take(10), size = 10.sp, translate = false, weight = FontWeight.Medium, color = if (on) p.text else p.muted, lines = 1)
                }
            }
        }
    }
}

/** Tizim brauzerida ochish. WebView ishlatilmaydi. */
fun openBrowser(ctx: android.content.Context, url: String) {
    runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
        .onFailure { Toasts.show("Brauzerni oçib bölmadi", "err") }
}
