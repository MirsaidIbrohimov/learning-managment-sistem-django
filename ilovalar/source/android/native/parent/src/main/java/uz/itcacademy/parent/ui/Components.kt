package uz.itcacademy.parent.ui

import android.text.Html
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.fromHtml
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import kotlinx.coroutines.delay
import uz.itcacademy.parent.Api
import uz.itcacademy.parent.ApiError
import uz.itcacademy.parent.t
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone

// ───────── Matn ─────────
@Composable
fun Txt(
    text: String,
    modifier: Modifier = Modifier,
    size: TextUnit = 14.sp,
    weight: FontWeight = FontWeight.Normal,
    color: Color = pal.text,
    lines: Int = Int.MAX_VALUE,
    align: TextAlign? = null,
    spacing: TextUnit = TextUnit.Unspecified,
    translate: Boolean = true,
) = Text(
    if (translate) t(text) else text, modifier, color = color, fontSize = size, fontWeight = weight, maxLines = lines,
    overflow = TextOverflow.Ellipsis, textAlign = align, letterSpacing = spacing,
)

@Composable
fun Muted(text: String, modifier: Modifier = Modifier, size: TextUnit = 12.5.sp, lines: Int = Int.MAX_VALUE, translate: Boolean = true) =
    Txt(text, modifier, size, color = pal.muted, lines = lines, translate = translate)

/** Saytdan kelgan tozalangan HTML: qalin, kursiv, ro'yxat va havolalar. */
@Composable
fun RichText(html: String, modifier: Modifier = Modifier, size: TextUnit = 14.sp, color: Color = pal.text2) {
    val prepared = remember(html) {
        html.replace(Regex("(?i)<li[^>]*>"), "<br>• ").replace(Regex("(?i)</li>|</?ul[^>]*>|</?ol[^>]*>"), "")
            .replace(Regex("(?i)<(/?)h[1-6][^>]*>")) { if (it.groupValues[1].isEmpty()) "<br><b>" else "</b><br>" }
    }
    val p = pal
    val text = remember(prepared, p.a1) {
        androidx.compose.ui.text.AnnotatedString.fromHtml(
            prepared,
            linkStyles = androidx.compose.ui.text.TextLinkStyles(androidx.compose.ui.text.SpanStyle(color = p.a1)),
        )
    }
    Text(text, modifier, color = color, fontSize = size, lineHeight = size * 1.45f)
}

@Composable
fun H1(text: String, sub: String? = null, modifier: Modifier = Modifier) {
    Column(modifier) {
        Txt(text, size = 30.sp, weight = FontWeight.Bold, spacing = (-.6).sp)
        if (sub != null) Muted(sub, Modifier.padding(top = 2.dp), 13.5.sp)
    }
}

@Composable
fun SectionTitle(text: String, icon: ImageVector? = null, more: String? = null, onMore: (() -> Unit)? = null) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().padding(bottom = 10.dp)) {
        if (icon != null) { Icon(icon, null, Modifier.size(18.dp), pal.text); Spacer(Modifier.width(8.dp)) }
        Txt(text, Modifier.weight(1f), 15.sp, FontWeight.SemiBold)
        if (more != null && onMore != null) {
            Row(Modifier.press(onClick = onMore), verticalAlignment = Alignment.CenterVertically) {
                Muted(more)
                Icon(Icons.Rounded.ChevronRight, null, Modifier.size(16.dp), pal.muted)
            }
        }
    }
}

// ───────── Format ─────────
private val MONTHS = listOf("yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr")

fun num(n: Number?): String {
    val v = n?.toLong() ?: 0L
    val s = kotlin.math.abs(v).toString().reversed().chunked(3).joinToString(" ").reversed()
    return if (v < 0) "-$s" else s
}

fun parseDate(s: String?): Date? {
    if (s.isNullOrBlank()) return null
    val clean = s.replace(Regex("\\.\\d+"), "").replace("Z", "+0000").replace(Regex("([+-]\\d{2}):(\\d{2})$"), "$1$2")
    for (f in listOf("yyyy-MM-dd'T'HH:mm:ssZ", "yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd")) {
        runCatching { return SimpleDateFormat(f, Locale.US).apply { if (!f.endsWith("Z")) timeZone = TimeZone.getDefault() }.parse(clean) }
    }
    return null
}

fun dateText(s: String?, withYear: Boolean = true): String {
    val d = parseDate(s) ?: return "—"
    val c = Calendar.getInstance().apply { time = d }
    val year = if (withYear) " ${c.get(Calendar.YEAR)}" else ""
    return "${c.get(Calendar.DAY_OF_MONTH)}-${MONTHS[c.get(Calendar.MONTH)]}$year"
}

fun timeText(s: String?): String {
    val d = parseDate(s) ?: return ""
    return SimpleDateFormat("HH:mm", Locale.US).format(d)
}

fun ago(s: String?): String {
    val d = parseDate(s) ?: return ""
    val sec = (System.currentTimeMillis() - d.time) / 1000
    return when {
        sec < 60 -> "hozirgina"
        sec < 3600 -> "${sec / 60} daqiqa oldin"
        sec < 86400 -> "${sec / 3600} soat oldin"
        sec < 86400 * 7 -> "${sec / 86400} kun oldin"
        else -> dateText(s)
    }
}

fun greeting(): String {
    val h = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
    return when { h < 5 -> "Xayrli tun"; h < 12 -> "Xayrli tong"; h < 18 -> "Xayrli kun"; else -> "Xayrli keç" }
}

fun stripHtml(s: String?): String =
    if (s.isNullOrBlank()) "" else Html.fromHtml(s, Html.FROM_HTML_MODE_COMPACT).toString().replace(Regex("\\s+"), " ").trim()

fun initials(name: String?): String =
    (name ?: "?").trim().split(Regex("\\s+")).take(2).mapNotNull { it.firstOrNull()?.toString() }.joinToString("").uppercase().ifEmpty { "?" }

private val TINTS = listOf(
    0xFF7C3AED to 0xFFDB2777, 0xFF2563EB to 0xFF06B6D4, 0xFF059669 to 0xFF65A30D, 0xFFEA580C to 0xFFE11D48, 0xFF0891B2 to 0xFF6366F1,
    0xFF9333EA to 0xFF4F46E5, 0xFFD97706 to 0xFFDC2626, 0xFF0D9488 to 0xFF2563EB, 0xFFBE185D to 0xFF7C3AED, 0xFF4F46E5 to 0xFF0EA5E9,
)

fun tint(key: String?): Brush {
    var h = 0L
    (key ?: "").forEach { h = (h * 31 + it.code) and 0xFFFFFFFFL }
    val (a, b) = TINTS[(h % TINTS.size).toInt()]
    return Brush.linearGradient(listOf(Color(a), Color(b)))
}

// ───────── Kichik elementlar ─────────
@Composable
fun Avatar(photo: String?, name: String?, size: Dp = 38.dp, ring: Color? = null) {
    Box(
        Modifier.size(size).then(if (ring != null) Modifier.border(2.dp, ring, CircleShape).padding(3.dp) else Modifier)
            .clip(CircleShape).background(tint(name)),
        contentAlignment = Alignment.Center,
    ) {
        Text(initials(name), color = Color.White, fontWeight = FontWeight.Bold, fontSize = (size.value * .36f).sp)
        Api.media(photo)?.let { AsyncImage(it, null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
    }
}

@Composable
fun CoinDot(size: Dp = 18.dp) {
    Box(
        Modifier.size(size).clip(CircleShape).background(
            Brush.radialGradient(listOf(Color(0xFFFDE68A), Color(0xFFF59E0B), Color(0xFFB45309))),
        ),
        contentAlignment = Alignment.Center,
    ) { Text("₵", color = Color(0xFF7C2D12), fontWeight = FontWeight.ExtraBold, fontSize = (size.value * .55f).sp) }
}

@Composable
fun Tag(text: String, color: Color = pal.text2, fill: Color = pal.surface2, icon: ImageVector? = null, translate: Boolean = true) {
    Row(
        Modifier.clip(RoundedCornerShape(20.dp)).background(fill).padding(horizontal = 9.dp, vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (icon != null) { Icon(icon, null, Modifier.size(12.dp), color); Spacer(Modifier.width(4.dp)) }
        Txt(text, size = 11.5.sp, weight = FontWeight.SemiBold, color = color, lines = 1, translate = translate)
    }
}

@Composable fun TagGreen(text: String, icon: ImageVector? = null) = Tag(text, pal.green, pal.green.copy(alpha = .14f), icon)
@Composable fun TagRed(text: String, icon: ImageVector? = null) = Tag(text, pal.red, pal.red.copy(alpha = .13f), icon)
@Composable fun TagAmber(text: String, icon: ImageVector? = null) = Tag(text, pal.amber, pal.amber.copy(alpha = .14f), icon)
@Composable fun TagBlue(text: String, icon: ImageVector? = null) = Tag(text, pal.blue, pal.blue.copy(alpha = .13f), icon)
@Composable fun TagAccent(text: String, icon: ImageVector? = null) = Tag(text, pal.a1, pal.a1.copy(alpha = .16f), icon)
@Composable fun TagPremium() = Tag(
    "Premium", Color.White, Color(0xFFF97316), Icons.Rounded.WorkspacePremium,
)

@Composable
fun IcoBox(icon: ImageVector, color: Color, size: Dp = 38.dp) {
    Tinted(color.copy(alpha = .16f), Modifier.size(size), RoundedCornerShape(size * .3f)) {
        Icon(icon, null, Modifier.size(size * .5f), color)
    }
}

enum class BtnKind { Primary, Normal, Ghost, Danger }

@Composable
fun Btn(
    text: String,
    modifier: Modifier = Modifier,
    kind: BtnKind = BtnKind.Normal,
    icon: ImageVector? = null,
    enabled: Boolean = true,
    busy: Boolean = false,
    small: Boolean = false,
    onClick: () -> Unit,
) {
    val p = pal
    val shape = RoundedCornerShape(if (small) 11.dp else 14.dp)
    val fg = when (kind) { BtnKind.Primary -> Color.White; BtnKind.Danger -> p.red; else -> p.text }
    val bgMod = when (kind) {
        BtnKind.Primary -> Modifier.background(Brush.linearGradient(listOf(p.a1, p.a2)), shape)
        BtnKind.Ghost -> Modifier
        BtnKind.Danger -> Modifier.background(p.red.copy(alpha = .12f), shape)
        BtnKind.Normal -> Modifier.background(p.surface2, shape).border(1.dp, p.border, shape)
    }
    Row(
        modifier.press(enabled && !busy, onClick = onClick)
            .graphicsLayer { alpha = if (enabled) 1f else .45f }
            .clip(shape).then(bgMod)
            .heightIn(min = if (small) 34.dp else 46.dp)
            .padding(horizontal = if (small) 12.dp else 18.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
    ) {
        if (busy) { Spinner(16.dp, fg); Spacer(Modifier.width(8.dp)) }
        else if (icon != null) { Icon(icon, null, Modifier.size(if (small) 15.dp else 18.dp), fg); Spacer(Modifier.width(7.dp)) }
        Txt(text, size = if (small) 12.5.sp else 14.5.sp, weight = FontWeight.SemiBold, color = fg, lines = 1)
    }
}

@Composable
fun Spinner(size: Dp = 22.dp, color: Color = pal.a1) {
    val tr = rememberInfiniteTransition(label = "spin")
    val r by tr.animateFloat(0f, 360f, infiniteRepeatable(tween(800, easing = androidx.compose.animation.core.LinearEasing)), label = "r")
    Canvas(Modifier.size(size).graphicsLayer { rotationZ = r }) {
        drawArc(color, 0f, 270f, false, style = Stroke(size.toPx() * .14f, cap = StrokeCap.Round))
    }
}

/** iOS almashtirgichi. */
@Composable
fun Switch(on: Boolean, onChange: (Boolean) -> Unit) {
    val x by animateDpAsState(if (on) 20.dp else 2.dp, spring(.68f, Spring.StiffnessMediumLow), label = "sw")
    Box(
        Modifier.size(48.dp, 28.dp).clip(RoundedCornerShape(28.dp))
            .background(if (on) Color(0xFF34C759) else pal.surface3)
            .press(scale = .97f) { onChange(!on) },
    ) {
        Box(Modifier.offset(x = x, y = 2.dp).size(24.dp).clip(CircleShape).background(Color.White))
    }
}

/** Segmentli tugma: tanlangan bo'lak sirpanib o'tadi. */
@Composable
fun Segmented(items: List<String>, selected: Int, modifier: Modifier = Modifier, onSelect: (Int) -> Unit) {
    val p = pal
    var w by remember { mutableIntStateOf(0) }
    val density = LocalDensity.current
    val itemW = with(density) { (w / items.size.coerceAtLeast(1)).toDp() }
    val x by animateDpAsState(itemW * selected, spring(.8f, Spring.StiffnessMediumLow), label = "seg")
    Box(
        modifier.fillMaxWidth().height(40.dp).clip(RoundedCornerShape(13.dp)).background(p.surface)
            .onSizeChanged { w = it.width - with(density) { 6.dp.roundToPx() } }.padding(3.dp),
    ) {
        if (w > 0) Box(
            Modifier.offset(x = x).width(itemW).fillMaxHeight().clip(RoundedCornerShape(10.dp))
                .background(if (p.dark) p.surface3 else Color.White),
        )
        Row(Modifier.fillMaxSize()) {
            items.forEachIndexed { i, s ->
                Box(Modifier.weight(1f).fillMaxHeight().press(scale = .95f) { onSelect(i) }, contentAlignment = Alignment.Center) {
                    Txt(s, size = 12.5.sp, weight = FontWeight.SemiBold, color = if (i == selected) p.text else p.muted, lines = 1)
                }
            }
        }
    }
}

@Composable
fun Chips(items: List<Pair<String, String>>, selected: String, modifier: Modifier = Modifier, onSelect: (String) -> Unit) {
    Row(modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items.forEach { (k, label) ->
            val on = k == selected
            Box(
                Modifier.press(scale = .95f) { onSelect(k) }.clip(RoundedCornerShape(20.dp))
                    .background(if (on) pal.a1 else pal.surface2).padding(horizontal = 13.dp, vertical = 7.dp),
            ) { Txt(label, size = 12.5.sp, weight = FontWeight.SemiBold, color = if (on) Color.White else pal.text2, lines = 1) }
        }
    }
}

@Composable
fun Field(
    value: String,
    onChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    password: Boolean = false,
    keyboard: KeyboardType = KeyboardType.Text,
    single: Boolean = true,
    minHeight: Dp = 46.dp,
    trailing: (@Composable () -> Unit)? = null,
) {
    val p = pal
    val shape = RoundedCornerShape(14.dp)
    Row(
        modifier.fillMaxWidth().heightIn(min = minHeight).clip(shape).background(p.surface).border(1.dp, p.border, shape)
            .padding(horizontal = 14.dp, vertical = if (single) 0.dp else 12.dp),
        verticalAlignment = if (single) Alignment.CenterVertically else Alignment.Top,
    ) {
        if (icon != null) { Icon(icon, null, Modifier.size(18.dp), p.muted); Spacer(Modifier.width(10.dp)) }
        Box(Modifier.weight(1f)) {
            if (value.isEmpty()) Muted(placeholder, size = 14.sp, lines = 1)
            BasicTextField(
                value, onChange, Modifier.fillMaxWidth().semantics { contentDescription = t(placeholder) }, singleLine = single,
                textStyle = TextStyle(color = p.text, fontSize = 14.5.sp),
                cursorBrush = SolidColor(p.a1),
                visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
                keyboardOptions = KeyboardOptions(keyboardType = if (password) KeyboardType.Password else keyboard),
            )
        }
        trailing?.invoke()
    }
}

/** Silliq sanaluvchi son. */
@Composable
fun CountUp(target: Int, size: TextUnit = 26.sp, color: Color = pal.text, weight: FontWeight = FontWeight.Bold) {
    val a = remember { Animatable(if (motionOn) 0f else target.toFloat()) }
    LaunchedEffect(target) { if (motionOn) a.animateTo(target.toFloat(), tween(900, easing = FastOutSlowInEasing)) else a.snapTo(target.toFloat()) }
    Text(num(a.value.toLong()), color = color, fontSize = size, fontWeight = weight, letterSpacing = (-.5).sp)
}

@Composable
fun ProgressBar(fraction: Float, modifier: Modifier = Modifier, color: Color? = null, track: Color = pal.surface3, height: Dp = 7.dp) {
    val g = growIn()
    val p = pal
    Canvas(modifier.fillMaxWidth().height(height)) {
        val r = CornerRadius(size.height / 2)
        drawRoundRect(track, cornerRadius = r)
        val w = size.width * fraction.coerceIn(0f, 1f) * g
        if (w > 0f) {
            if (color != null) drawRoundRect(color, size = Size(w, size.height), cornerRadius = r)
            else drawRoundRect(Brush.horizontalGradient(listOf(p.a1, p.a2)), size = Size(w, size.height), cornerRadius = r)
        }
    }
}

@Composable
fun Ring(percent: Int, size: Dp = 44.dp, color: Color = pal.a1, textSize: TextUnit = 11.sp) {
    val g = growIn(durationMs = 1100)
    val track = pal.surface3
    Box(Modifier.size(size), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val st = Stroke(this.size.width * .11f, cap = StrokeCap.Round)
            drawArc(track, 0f, 360f, false, style = st)
            drawArc(color, -90f, 360f * percent / 100f * g, false, style = st)
        }
        Text("$percent%", color = pal.text, fontSize = textSize, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun Shimmer(modifier: Modifier, shape: RoundedCornerShape = RoundedCornerShape(14.dp)) {
    val p = pal
    val tr = rememberInfiniteTransition(label = "sk")
    val a by tr.animateFloat(.5f, 1f, infiniteRepeatable(tween(850), androidx.compose.animation.core.RepeatMode.Reverse), label = "a")
    Box(modifier.graphicsLayer { alpha = a }.clip(shape).background(p.surface2))
}

@Composable
fun SkeletonList(n: Int = 6, h: Dp = 68.dp) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) { repeat(n) { Shimmer(Modifier.fillMaxWidth().height(h)) } }
}

@Composable
fun EmptyState(icon: ImageVector, title: String, text: String = "", action: (@Composable () -> Unit)? = null) {
    val tr = rememberInfiniteTransition(label = "em")
    val y by tr.animateFloat(0f, if (motionOn) -8f else 0f, infiniteRepeatable(tween(1800), androidx.compose.animation.core.RepeatMode.Reverse), label = "y")
    Column(Modifier.fillMaxWidth().padding(vertical = 38.dp, horizontal = 20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Tinted(pal.surface2, Modifier.size(72.dp).graphicsLayer { translationY = y }, RoundedCornerShape(22.dp)) {
            Icon(icon, null, Modifier.size(32.dp), pal.text2)
        }
        Spacer(Modifier.height(14.dp))
        Txt(title, size = 17.sp, weight = FontWeight.SemiBold, align = TextAlign.Center)
        if (text.isNotEmpty()) Muted(text, Modifier.padding(top = 4.dp), 13.5.sp)
        if (action != null) { Spacer(Modifier.height(14.dp)); action() }
    }
}

@Composable
fun ErrorState(e: Throwable, onRetry: () -> Unit) {
    val offline = (e as? ApiError)?.status == 0
    val msg = e.message.orEmpty()
    EmptyState(if (offline) Icons.Rounded.WifiOff else Icons.Rounded.ErrorOutline, if (offline) "Aloqa yöq" else "Yuklab bölmadi", msg) {
        Btn("Qayta urinish", icon = Icons.Rounded.Refresh, onClick = onRetry)
    }
}

/** Ro'yxatdagi qator. */
@Composable
fun Row2(
    title: String,
    sub: String = "",
    modifier: Modifier = Modifier,
    leading: (@Composable () -> Unit)? = null,
    trailing: (@Composable () -> Unit)? = null,
    translate: Boolean = true,
    onClick: (() -> Unit)? = null,
) {
    Row(
        modifier.fillMaxWidth().then(if (onClick != null) Modifier.press(scale = .985f, onClick = onClick) else Modifier).padding(vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (leading != null) { leading(); Spacer(Modifier.width(12.dp)) }
        Column(Modifier.weight(1f)) {
            Txt(title, weight = FontWeight.SemiBold, lines = 2, translate = translate)
            if (sub.isNotEmpty()) Muted(sub, lines = 2)
        }
        if (trailing != null) { Spacer(Modifier.width(10.dp)); trailing() }
    }
}

@Composable fun Hairline() = Box(Modifier.fillMaxWidth().height(1.dp).background(pal.border))

/** Yuklash holati: skelet, xato yoki ma'lumot. */
class Load<T>(val data: T?, val error: Throwable?, val loading: Boolean, val retry: () -> Unit)

@Composable
fun <T> rememberLoad(vararg keys: Any?, block: suspend () -> T): Load<T> {
    var data by remember { mutableStateOf<T?>(null) }
    var error by remember { mutableStateOf<Throwable?>(null) }
    var loading by remember { mutableStateOf(true) }
    var tick by remember { mutableIntStateOf(0) }
    LaunchedEffect(tick, *keys) {
        loading = true
        error = null
        try {
            data = block()
        } catch (e: ApiError) {
            error = e
        }
        loading = false
    }
    return Load(data, error, loading) { tick++ }
}

@Composable
fun Page(modifier: Modifier = Modifier, bottom: Dp = 120.dp, top: Dp = 0.dp, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .statusBarsPadding().padding(top = top + 10.dp, start = 16.dp, end = 16.dp, bottom = bottom),
        verticalArrangement = Arrangement.spacedBy(14.dp),
        content = content,
    )
}

/** Yuqoridagi orqaga tugmasi va sarlavha. */
@Composable
fun BackHeader(title: String, sub: String? = null, onBack: () -> Unit, trailing: (@Composable () -> Unit)? = null) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Tinted(pal.surface2, Modifier.size(40.dp).press(onClick = onBack), CircleShape) {
            Icon(Icons.Rounded.ChevronLeft, t("Orqaga"), Modifier.size(24.dp), pal.text)
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Txt(title, size = 19.sp, weight = FontWeight.Bold, lines = 1)
            if (sub != null) Muted(sub, lines = 1)
        }
        trailing?.invoke()
    }
}

/** Xabar: Dynamic Island kabi yuqoridan tushadi. */
object Toasts {
    data class T(val msg: String, val kind: String, val id: Long = System.nanoTime())
    var current by mutableStateOf<T?>(null)
    fun show(msg: String, kind: String = "ok") { current = T(msg, kind) }
}

@Composable
fun ToastHost() {
    val cur = Toasts.current
    LaunchedEffect(cur?.id) { if (cur != null) { delay(3400); Toasts.current = null } }
    Box(Modifier.fillMaxWidth().statusBarsPadding().padding(top = 8.dp, start = 16.dp, end = 16.dp), contentAlignment = Alignment.TopCenter) {
        AnimatedVisibility(
            cur != null,
            enter = slideInVertically(spring(.62f, Spring.StiffnessMediumLow)) { -it * 2 } + fadeIn(),
            exit = slideOutVertically { -it } + fadeOut(),
        ) {
            var last by remember { mutableStateOf(cur) }
            if (cur != null) last = cur
            val c = last ?: return@AnimatedVisibility
            val color = when (c.kind) { "err" -> pal.red; "info" -> pal.a1; else -> pal.green }
            Row(
                Modifier.glassBlur(RoundedCornerShape(24.dp)).padding(horizontal = 14.dp, vertical = 11.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (c.kind == "coin") CoinDot(22.dp)
                else Icon(if (c.kind == "err") Icons.Rounded.ErrorOutline else if (c.kind == "info") Icons.Rounded.Info else Icons.Rounded.CheckCircle, null, Modifier.size(22.dp), color)
                Spacer(Modifier.width(10.dp))
                Txt(c.msg, weight = FontWeight.Medium)
            }
        }
    }
}

/** iOS varag'i: pastdan ko'tariladi, orqa fon xiralashadi. */
object Sheets {
    class S(val content: @Composable (close: () -> Unit) -> Unit, val id: Long = System.nanoTime())
    val stack = mutableStateListOf<S>()
    fun show(content: @Composable (close: () -> Unit) -> Unit) { stack += S(content) }
    fun closeTop(): Boolean { if (stack.isEmpty()) return false; stack.removeAt(stack.lastIndex); return true }

    fun confirm(title: String, text: String, ok: String = "Tasdiqlaş", danger: Boolean = false, onOk: () -> Unit) = show { close ->
        Txt(title, size = 19.sp, weight = FontWeight.Bold)
        Muted(text, Modifier.padding(top = 8.dp, bottom = 18.dp), 14.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Btn("Bekor qiliş", Modifier.weight(1f), onClick = close)
            Btn(ok, Modifier.weight(1f), if (danger) BtnKind.Danger else BtnKind.Primary) { close(); onOk() }
        }
    }
}

@Composable
fun SheetHost() {
    Sheets.stack.forEach { s ->
        key(s.id) {
            val anim = remember { Animatable(0f) }
            var closing by remember { mutableStateOf(false) }
            val close: () -> Unit = { closing = true }
            LaunchedEffect(closing) {
                if (closing) {
                    anim.animateTo(0f, tween(170))
                    Sheets.stack.remove(s)
                } else anim.animateTo(1f, spring(.82f, Spring.StiffnessMediumLow))
            }
            androidx.activity.compose.BackHandler { close() }
            Box(
                Modifier.fillMaxSize().graphicsLayer { alpha = anim.value.coerceIn(0f, 1f) }.background(Color(0x66050412))
                    .clickable(remember { MutableInteractionSource() }, null) { close() },
                contentAlignment = Alignment.BottomCenter,
            ) {
                Column(
                    Modifier.fillMaxWidth().imePadding().navigationBarsPadding().padding(8.dp)
                        .graphicsLayer { translationY = (1f - anim.value) * 500f }
                        .glassBlur(RoundedCornerShape(30.dp), if (pal.dark) Color(0xD91A1A28) else Color(0xEBFFFFFF))
                        .clickable(remember { MutableInteractionSource() }, null) { }
                        .heightIn(max = 680.dp).verticalScroll(rememberScrollState()).padding(20.dp),
                ) {
                    Box(Modifier.align(Alignment.CenterHorizontally).size(38.dp, 5.dp).clip(CircleShape).background(pal.surface3))
                    Spacer(Modifier.height(14.dp))
                    s.content(close)
                }
            }
        }
    }
}

// ───────── Grafik ─────────
data class ChartPoint(val label: String, val value: Int, val highlight: Boolean = false)

/** Haftalik ustunli grafik: bosilgan kun ustida qiymat chiqadi. */
@Composable
fun ColumnChart(data: List<ChartPoint>, modifier: Modifier = Modifier, unit: String = "ta faollik") {
    val p = pal
    val g = growIn(durationMs = 900)
    var sel by remember(data) { mutableIntStateOf(-1) }
    val max = (data.maxOfOrNull { it.value } ?: 1).coerceAtLeast(1)
    Column(modifier) {
        Box(Modifier.height(22.dp)) {
            if (sel in data.indices) Txt("${data[sel].label}: ${num(data[sel].value)} $unit", size = 12.5.sp, weight = FontWeight.SemiBold, color = p.text2)
        }
        Canvas(
            Modifier.fillMaxWidth().height(110.dp).pointerInput(data) {
                detectTapGestures { o -> sel = (o.x / size.width * data.size).toInt().coerceIn(0, data.lastIndex) }
            },
        ) {
            val slot = size.width / data.size
            val w = slot * .56f
            data.forEachIndexed { i, d ->
                val h = if (d.value == 0) 4.dp.toPx() else (size.height * d.value / max * g).coerceAtLeast(4.dp.toPx())
                drawRoundRect(
                    if (d.value == 0) SolidColor(p.surface3) else if (i == sel || d.highlight) SolidColor(p.a2) else SolidColor(p.a1),
                    Offset(i * slot + (slot - w) / 2, size.height - h), Size(w, h), CornerRadius(6.dp.toPx()),
                )
            }
        }
        Row(Modifier.fillMaxWidth().padding(top = 6.dp)) {
            data.forEach { d ->
                Box(Modifier.weight(1f), contentAlignment = Alignment.Center) {
                    Muted(d.label, size = 10.5.sp, lines = 1, translate = false)
                }
            }
        }
    }
}
