package uz.itcacademy.parent.screens

import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.Icon
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import org.json.JSONObject
import uz.itcacademy.parent.*
import uz.itcacademy.parent.ui.*

/** Farzandlar almashtirgichi: bitta farzand bo'lsa ham ismi ko'rinib turadi. */
@Composable
fun ChildSwitcher(modifier: Modifier = Modifier) {
    val kids = AppState.children
    if (kids.isEmpty()) return
    Row(modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        kids.forEach { c ->
            val on = c.int("id") == AppState.child?.int("id")
            val p = pal
            Row(
                Modifier.press(scale = .94f) { AppState.selectChild(c.int("id")) }
                    .clip(RoundedCornerShape(30.dp))
                    .then(
                        if (on) Modifier.background(Brush.linearGradient(listOf(p.a1, p.a2)))
                        else Modifier.background(p.surface2),
                    )
                    .padding(start = 5.dp, end = 14.dp, top = 5.dp, bottom = 5.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Avatar(c.strOrNull("photo"), c.str("name"), 28.dp)
                Spacer(Modifier.width(8.dp))
                Txt(c.str("first_name").ifEmpty { c.str("name") }, size = 13.5.sp, weight = FontWeight.SemiBold,
                    color = if (on) Color.White else p.text, lines = 1, translate = false)
            }
        }
    }
}

/** Qo'ng'iroqcha: o'qilmagan bildirishnomalar soni bilan. */
@Composable
fun Bell() {
    val p = pal
    val n = AppState.unreadNotif
    val sc by animateFloatAsState(if (n > 0) 1f else 0f, spring(.5f, Spring.StiffnessMedium), label = "badge")
    Box(Modifier.size(44.dp).press { AppState.open(Route.Notifications) }) {
        Tinted(p.surface2, Modifier.fillMaxSize(), CircleShape) {
            Icon(Icons.Rounded.Notifications, "Bildirişnomalar", Modifier.size(22.dp), p.text)
        }
        if (n > 0) Box(
            Modifier.align(Alignment.TopEnd).graphicsLayer { scaleX = sc; scaleY = sc }
                .size(19.dp).clip(CircleShape).background(p.red),
            contentAlignment = Alignment.Center,
        ) { Txt(if (n > 9) "9+" else "$n", size = 10.sp, weight = FontWeight.Bold, color = Color.White) }
    }
}

/** Bo'lim sarlavhasi: nom, farzand tanlagich va qo'ng'iroqcha. */
@Composable
fun TabHeader(title: String, sub: String? = null) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            H1(title, sub, Modifier.weight(1f))
            Bell()
        }
        if (AppState.children.size > 1) ChildSwitcher()
    }
}

/** Tanlangan farzand bo'yicha yuklash. Farzand o'zgarsa qayta yuklanadi. */
@Composable
fun rememberChildLoad(part: String): Load<JSONObject> {
    val id = AppState.child?.int("id") ?: 0
    // key: boshqa farzand/bo'limga o'tilganda eski ma'lumot bir lahza ham ko'rinmaydi
    return key(id, part) { rememberLoad { Api.get("children/$id/$part") } }
}

/** Pastga tortib yangilash. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Refreshable(onRefresh: suspend () -> Unit, content: @Composable () -> Unit) {
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    PullToRefreshBox(busy, onRefresh = {
        scope.launch {
            busy = true
            Api.clearCache()
            runCatching { onRefresh() }
            busy = false
        }
    }) { content() }
}

@Composable
fun NoChild() = EmptyState(
    Icons.Rounded.FamilyRestroom, "Farzand biriktirilmagan",
    "Hisobingizga hali farzand qöşilmagan. Öquv markazi administratoriga murojaat qiling.",
)

/** Kichik ko'rsatkich: ikonka, qiymat, nom. */
@Composable
fun Stat(icon: ImageVector, color: Color, value: String, label: String, modifier: Modifier = Modifier) {
    Column(modifier.card(RoundedCornerShape(18.dp)).padding(12.dp)) {
        IcoBox(icon, color, 34.dp)
        Spacer(Modifier.height(10.dp))
        Txt(value, size = 19.sp, weight = FontWeight.Bold, lines = 1)
        Muted(label, lines = 1)
    }
}

/** Ogohlantirish darajasi ranglari. */
@Composable
fun levelColor(level: String): Color = when (level) {
    "danger" -> pal.red
    "warning" -> pal.amber
    "success" -> pal.green
    else -> pal.blue
}

fun levelIcon(level: String): ImageVector = when (level) {
    "danger" -> Icons.Rounded.ErrorOutline
    "warning" -> Icons.Rounded.WarningAmber
    "success" -> Icons.Rounded.CheckCircle
    else -> Icons.Rounded.Info
}

/** Voqea turi bo'yicha ikonka va rang (bildirishnomalar, faollik). */
@Composable
fun kindStyle(kind: String): Pair<ImageVector, Color> {
    val p = pal
    return when (kind) {
        "test_pass", "test" -> Icons.Rounded.TaskAlt to p.green
        "test_fail" -> Icons.Rounded.HighlightOff to p.red
        "homework_graded", "homework" -> Icons.Rounded.Grading to p.a1
        "homework_revision" -> Icons.Rounded.Replay to p.amber
        "speaking_graded" -> Icons.Rounded.RecordVoiceOver to p.a2
        "absent" -> Icons.Rounded.PersonOff to p.red
        "late" -> Icons.Rounded.Schedule to p.amber
        "certificate" -> Icons.Rounded.WorkspacePremium to p.amber
        "payment_ok" -> Icons.Rounded.Paid to p.green
        "payment_due" -> Icons.Rounded.EventNote to p.amber
        "reply" -> Icons.Rounded.Forum to p.blue
        "notice" -> Icons.Rounded.Campaign to p.blue
        "video" -> Icons.Rounded.PlayCircle to p.blue
        else -> Icons.Rounded.Notifications to p.a1
    }
}

/** Ballga qarab rang: 80+ yashil, 60+ sariq, qolgani qizil. */
@Composable
fun scoreColor(score: Number): Color = when {
    score.toDouble() >= 80 -> pal.green
    score.toDouble() >= 60 -> pal.amber
    else -> pal.red
}

fun som(n: Number?): String = "${num(n)} söm"

@Composable
fun Dot(color: Color, size: Dp = 8.dp) = Box(Modifier.size(size).clip(CircleShape).background(color))

/** "Sana" ajratgichi bo'yicha guruhlash uchun kun nomi. */
fun dayLabel(iso: String?): String {
    val d = parseDate(iso) ?: return ""
    val cal = java.util.Calendar.getInstance()
    val today = cal.get(java.util.Calendar.DAY_OF_YEAR) to cal.get(java.util.Calendar.YEAR)
    cal.add(java.util.Calendar.DAY_OF_YEAR, -1)
    val yest = cal.get(java.util.Calendar.DAY_OF_YEAR) to cal.get(java.util.Calendar.YEAR)
    cal.time = d
    val day = cal.get(java.util.Calendar.DAY_OF_YEAR) to cal.get(java.util.Calendar.YEAR)
    return when (day) { today -> "Bugun"; yest -> "Keça"; else -> dateText(iso) }
}
