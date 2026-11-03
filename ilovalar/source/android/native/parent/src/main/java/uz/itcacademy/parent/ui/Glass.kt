package uz.itcacademy.parent.ui

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.HazeStyle
import dev.chrisbanes.haze.HazeTint
import dev.chrisbanes.haze.hazeEffect
import kotlinx.coroutines.delay
import uz.itcacademy.parent.Settings

/** glass.css bilan bir xil ranglar. */
class Pal(
    val dark: Boolean,
    val bg: Color, val surface: Color, val surface2: Color, val surface3: Color, val solid: Color,
    val border: Color, val border2: Color, val highlight: Color,
    val text: Color, val text2: Color, val muted: Color,
    val green: Color, val red: Color, val amber: Color, val blue: Color,
    val a1: Color, val a2: Color, val a3: Color,
)

private val ACCENTS = mapOf(
    "violet" to Triple(Color(0xFF8B5CF6), Color(0xFFD946EF), Color(0xFFEC4899)),
    "ocean" to Triple(Color(0xFF3B82F6), Color(0xFF06B6D4), Color(0xFF22D3EE)),
    "emerald" to Triple(Color(0xFF10B981), Color(0xFF14B8A6), Color(0xFF84CC16)),
    "sunset" to Triple(Color(0xFFF97316), Color(0xFFEF4444), Color(0xFFEC4899)),
)

fun palette(dark: Boolean, accent: String): Pal {
    val (a1, a2, a3) = ACCENTS[accent] ?: ACCENTS.getValue("violet")
    return if (dark) Pal(
        true, Color(0xFF05050F), Color(0x11FFFFFF), Color(0x1BFFFFFF), Color(0x29FFFFFF), Color(0xD91A1A28),
        Color(0x1AFFFFFF), Color(0x2EFFFFFF), Color(0x24FFFFFF),
        Color(0xFFEEEDF7), Color(0xFFB4B3C9), Color(0xFF8E8DA6),
        Color(0xFF34D399), Color(0xFFF87171), Color(0xFFFBBF24), Color(0xFF60A5FA), a1, a2, a3,
    ) else Pal(
        false, Color(0xFFE7EAF6), Color(0x94FFFFFF), Color(0xB8FFFFFF), Color(0x33787896), Color(0xE6FFFFFF),
        Color(0x171E1A46), Color(0x291E1A46), Color(0xE6FFFFFF),
        Color(0xFF16142B), Color(0xFF45425F), Color(0xFF6E6B88),
        Color(0xFF059669), Color(0xFFDC2626), Color(0xFFB45309), Color(0xFF2563EB), a1, a2, a3,
    )
}

val LocalPal = compositionLocalOf { palette(true, "violet") }
val LocalHaze = compositionLocalOf { HazeState() }
val pal: Pal @Composable get() = LocalPal.current

@Composable
fun GlassTheme(dark: Boolean, content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalPal provides palette(dark, Settings.accent), content = content)
}

val CardShape = RoundedCornerShape(22.dp)
val motionOn: Boolean get() = Settings.motion

/** Sekin suzuvchi rangli fon. Faqat chizish bosqichida ishlaydi, sahifani qayta qurmaydi. */
@Composable
fun Wallpaper(modifier: Modifier = Modifier) {
    val p = pal
    val alpha = if (p.dark) 1f else .75f
    val move = remember { mutableStateOf(0f) }
    if (motionOn) LaunchedEffect(Unit) {
        val start = System.currentTimeMillis()
        while (true) {
            val phase = ((System.currentTimeMillis() - start) % 68_000L) / 34_000f
            move.value = if (phase <= 1f) phase else 2f - phase
            delay(80)
        }
    }
    Box(
        modifier.fillMaxSize().background(p.bg).drawBehind {
            val m = move.value
            val w = size.width
            val h = size.height
            val r = maxOf(w, h)
            fun blob(c: Color, x: Float, y: Float, rad: Float, a: Float) = drawCircle(
                Brush.radialGradient(listOf(c.copy(alpha = a * alpha), Color.Transparent), Offset(x, y), rad),
                radius = rad, center = Offset(x, y),
            )
            blob(p.a1, w * (.15f + .12f * m), h * (.12f + .08f * m), r * .62f, .46f)
            blob(p.a2, w * (.92f - .1f * m), h * (.1f + .1f * m), r * .52f, .38f)
            blob(p.a3, w * (.78f - .14f * m), h * (.82f - .08f * m), r * .55f, .3f)
            blob(Color(0xFF22D3EE), w * (.15f + .16f * m), h * (.85f - .1f * m), r * .48f, .24f)
        },
    )
}

/** Shisha panel: ortidagi kontent haqiqatan xiralashadi (Android 12+), eskisida shaffof fon. */
@Composable
fun Modifier.glassBlur(shape: Shape = CardShape, tint: Color? = null): Modifier {
    val p = pal
    val state = LocalHaze.current
    val t = tint ?: if (p.dark) Color(0x80101020) else Color(0x99FFFFFF)
    return this.clip(shape).hazeEffect(
        state,
        HazeStyle(backgroundColor = p.bg, tints = listOf(HazeTint(t)), blurRadius = 28.dp, noiseFactor = 0f),
    ).border(1.dp, p.border2, shape)
}

/** Oddiy karta: shaffof, ustida yorug'lik chizig'i. Har kartaga blur qo'yilmaydi, aylantirish silliq qoladi. */
@Composable
fun Modifier.card(shape: Shape = CardShape, fill: Color? = null): Modifier {
    val p = pal
    return this.clip(shape).background(fill ?: p.surface, shape).border(
        1.dp,
        Brush.verticalGradient(listOf(p.highlight, p.border)),
        shape,
    )
}

@Composable
fun GlassCard(
    modifier: Modifier = Modifier,
    pad: Dp = 18.dp,
    fill: Color? = null,
    content: @Composable ColumnScope.() -> Unit,
) = Column(modifier.card(fill = fill).padding(pad), content = content)

/** iOS uslubida bosilish: prujina bilan kichrayadi va yengil tebranish beradi. */
fun Modifier.press(enabled: Boolean = true, haptic: Boolean = true, scale: Float = .96f, onClick: () -> Unit): Modifier = composed {
    val src = remember { MutableInteractionSource() }
    val down by src.collectIsPressedAsState()
    val h = LocalHapticFeedback.current
    val s by animateFloatAsState(
        if (down && enabled && motionOn) scale else 1f,
        spring(Spring.DampingRatioMediumBouncy, Spring.StiffnessMedium),
        label = "press",
    )
    this
        .graphicsLayer { scaleX = s; scaleY = s }
        .clickable(src, null, enabled) {
            if (haptic) h.performHapticFeedback(HapticFeedbackType.TextHandleMove)
            onClick()
        }
}

/** Ketma-ket kirib kelish. rememberSaveable: ro'yxatga qaytganda takrorlanmaydi. */
fun Modifier.reveal(index: Int = 0): Modifier = composed {
    if (!motionOn) return@composed this
    var done by rememberSaveable { mutableStateOf(false) }
    if (done) return@composed this
    val a = remember { Animatable(0f) }
    LaunchedEffect(Unit) {
        delay(index.coerceAtMost(10) * 38L)
        a.animateTo(1f, spring(Spring.DampingRatioLowBouncy, Spring.StiffnessLow))
        done = true
    }
    graphicsLayer {
        val v = a.value
        alpha = v.coerceIn(0f, 1f)
        translationY = (1f - v) * 44f
        val sc = .975f + .025f * v
        scaleX = sc
        scaleY = sc
    }
}

/** Kiruvchi animatsiya uchun: 0 dan 1 gacha o'sib boradi (progress, ustunlar). */
@Composable
fun growIn(delayMs: Int = 0, durationMs: Int = 1000): Float {
    val a = remember { Animatable(if (motionOn) 0f else 1f) }
    LaunchedEffect(Unit) {
        if (motionOn) a.animateTo(1f, tween(durationMs, delayMs, FastOutSlowInEasing))
    }
    return a.value
}

@Composable
fun Tinted(color: Color, modifier: Modifier = Modifier, shape: Shape = RoundedCornerShape(13.dp), content: @Composable BoxScope.() -> Unit) {
    Box(modifier.clip(shape).background(color), contentAlignment = androidx.compose.ui.Alignment.Center, content = content)
}
