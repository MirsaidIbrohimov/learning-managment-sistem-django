package uz.itcacademy.lms

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.VolumeOff
import androidx.compose.material.icons.automirrored.rounded.VolumeUp
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import uz.itcacademy.lms.ui.press
import kotlin.math.PI
import kotlin.math.pow
import kotlin.math.sin
import kotlin.random.Random

private const val NAME_A = "IT Creative"
private const val NAME_B = "Academy"
private const val GLYPHS = "{}[]<>/=;:01$#_"
private const val START = 350L
private const val STEP = 55L
private const val RESOLVE = 160L
private const val IMPACT = 1550L
private const val HOLD = 2700L
private const val MAX_WAIT = 7000L

/** Saytdagi intro bilan bir xil g'oya: kursor o'tadi, kod belgilari nomga aylanadi, zarba va akkord. */
@Composable
fun IntroOverlay(ready: Boolean, onDone: () -> Unit) {
    if (!Settings.motion) {
        LaunchedEffect(ready) { if (ready) onDone() }
        return
    }
    val full = "$NAME_A $NAME_B"
    var now by remember { mutableLongStateOf(0L) }
    val punch = remember { Animatable(1f) }
    val rule = remember { Animatable(0f) }
    val slide = remember { Animatable(0f) }
    var sound by remember { mutableStateOf(Settings.sound) }
    val player = remember { IntroSound() }
    val readyState by rememberUpdatedState(ready)

    LaunchedEffect(Unit) { if (sound) player.play() }
    DisposableEffect(Unit) { onDispose { player.release() } }
    LaunchedEffect(Unit) {
        val t0 = withFrameMillis { it }
        var impacted = false
        while (isActive) {
            val t = withFrameMillis { it } - t0
            now = t
            if (!impacted && t >= IMPACT) {
                impacted = true
                launch { punch.animateTo(1.035f, tween(90)); punch.animateTo(1f, spring(.45f, Spring.StiffnessLow)) }
                launch { rule.animateTo(1f, spring(.8f, Spring.StiffnessLow)) }
            }
            if ((t >= HOLD && readyState) || t >= MAX_WAIT) break
        }
        slide.animateTo(1f, tween(620, easing = androidx.compose.animation.core.CubicBezierEasing(.76f, 0f, .24f, 1f)))
        onDone()
    }

    fun letter(i: Int): Pair<String, Int> {
        // 0: ko'rinmaydi, 1: kod belgisi, 2: tayyor harf
        val appear = START + i * STEP
        return when {
            now < appear -> full[i].toString() to 0
            full[i] == ' ' || now >= appear + RESOLVE -> full[i].toString() to 2
            else -> GLYPHS[Random.nextInt(GLYPHS.length)].toString() to 1
        }
    }

    Box(
        Modifier.fillMaxSize().clickable(remember { MutableInteractionSource() }, null) { }.graphicsLayer {
            translationY = -size.height * slide.value * 1.02f
        }.drawBehind {
            // Qatlamlar kechikib ko'tariladi: to'q fon, ko'k va havorang chiziq
            drawRect(Color(0xFF22D3EE), Offset(0f, size.height * (1f + .0f)), Size(size.width, size.height * .05f))
            drawRect(Color(0xFF6366F1), Offset(0f, size.height * 1f), Size(size.width, size.height * .025f))
            drawRect(Color(0xFF0B0A24))
        },
        contentAlignment = Alignment.Center,
    ) {
        Column(
            Modifier.graphicsLayer { scaleX = punch.value; scaleY = punch.value }.width(IntrinsicSize.Max),
            horizontalAlignment = Alignment.Start,
        ) {
            var offset = 0
            listOf(NAME_A, NAME_B).forEach { word ->
                val base = offset
                Row(verticalAlignment = Alignment.CenterVertically) {
                    word.forEachIndexed { j, _ ->
                        val (ch, state) = letter(base + j)
                        val idx = base + j
                        val caretAt = ((now - START) / STEP).toInt()
                        val blink = now < START && idx == 0 && (now / 350) % 2 == 0L
                        val running = now in START until IMPACT && caretAt == idx
                        Box(
                            Modifier.drawBehind {
                                if (blink || running) {
                                    val w = 3.dp.toPx()
                                    drawRect(
                                        Color(0xFF22D3EE),
                                        Offset(if (blink) 0f else size.width - w, size.height * .12f),
                                        Size(w, size.height * .76f),
                                    )
                                }
                            },
                            contentAlignment = Alignment.Center,
                        ) {
                            // Harf kengligi doim asl harfniki: belgilar almashganda matn sakramaydi
                            Text(word[j].toString(), color = Color.Transparent, fontSize = 50.sp, fontWeight = FontWeight.Bold, letterSpacing = (-1.2).sp)
                            if (state > 0) Text(
                                ch,
                                color = if (state == 1) Color(0xFF22D3EE) else Color(0xFFF4F5FF),
                                fontSize = if (state == 1) 42.sp else 50.sp,
                                fontWeight = if (state == 1) FontWeight.Medium else FontWeight.Bold,
                                fontFamily = if (state == 1) FontFamily.Monospace else FontFamily.Default,
                                letterSpacing = (-1.2).sp,
                            )
                        }
                    }
                }
                offset = end(base, word)
            }
            Spacer(Modifier.height(8.dp))
            Box(
                Modifier.fillMaxWidth().height(4.dp).graphicsLayer {
                    scaleX = rule.value
                    transformOrigin = androidx.compose.ui.graphics.TransformOrigin(0f, .5f)
                }.background(Brush.horizontalGradient(listOf(Color(0xFF22D3EE), Color(0xFF6366F1), Color(0xFFA855F7)))),
            )
        }
        Box(Modifier.fillMaxSize().navigationBarsPadding().padding(22.dp), contentAlignment = Alignment.BottomEnd) {
            Box(
                Modifier.size(44.dp).press {
                    sound = !sound
                    Settings.update { this.sound = sound }
                    if (sound) player.play() else player.stop()
                }.border(1.dp, Color(0x40F4F5FF), CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    if (sound) Icons.AutoMirrored.Rounded.VolumeUp else Icons.AutoMirrored.Rounded.VolumeOff,
                    t(if (sound) "Ovozni öçiriş" else "Ovozni yoqiş"), Modifier.size(20.dp), Color(0xFFF4F5FF),
                )
            }
        }
    }
}

private fun end(base: Int, word: String) = base + word.length + 1

/** Intro ovozi: sayt bilan bir xil notalar, kod ichida sintez qilinadi. Fayl kerak emas. */
class IntroSound {
    private var track: AudioTrack? = null
    private val scope = kotlinx.coroutines.CoroutineScope(Dispatchers.Default)
    private var job: kotlinx.coroutines.Job? = null

    fun play() {
        stop()
        job = scope.launch {
            val pcm = render()
            withContext(Dispatchers.Main) { start(pcm) }
        }
    }

    private fun start(pcm: ShortArray) {
        val t = AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANCE_SONIFICATION).setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build())
            .setAudioFormat(AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_16BIT).setSampleRate(RATE).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
            .setTransferMode(AudioTrack.MODE_STATIC)
            .setBufferSizeInBytes(pcm.size * 2)
            .build()
        t.write(pcm, 0, pcm.size)
        t.play()
        track = t
    }

    fun stop() {
        job?.cancel()
        track?.let { runCatching { it.stop() }; it.release() }
        track = null
    }

    fun release() = scope.launch { delay(3000); withContext(Dispatchers.Main) { stop() } }

    private fun render(): ShortArray {
        val total = (RATE * 3.6).toInt()
        val mix = FloatArray(total)
        val impact = IMPACT / 1000.0

        fun add(startSec: Double, dur: Double, sample: (Double) -> Double) {
            val from = (startSec * RATE).toInt()
            val n = (dur * RATE).toInt()
            for (i in 0 until n) {
                val at = from + i
                if (at in 0 until total) mix[at] += sample(i.toDouble() / RATE).toFloat()
            }
        }

        // Ko'tariluvchi shovqin: kursor yugurishi bilan
        var lp = 0.0
        add(0.05, impact - 0.05, ) { t ->
            val x = t / (impact - 0.05)
            val a = 0.02 + 0.45 * x * x
            lp += (0.02 + 0.5 * x * x) * ((Random.nextDouble() * 2 - 1) - lp)
            (Random.nextDouble() * 2 - 1 - lp) * a * 0.32 * x
        }
        // Har harf uchun chertish
        for (i in 0 until "$NAME_A $NAME_B".length) {
            val f = 1500.0 + (i % 5) * 170
            add((START + i * STEP) / 1000.0, 0.03) { t ->
                val env = (1 - t / 0.03).pow(2)
                (if (sin(2 * PI * f * t) > 0) 1.0 else -1.0) * 0.05 * env
            }
        }
        // Zarba: past "bum"
        add(impact, 0.62) { t ->
            val f = 42 + 78 * (1 - (t / 0.42).coerceAtMost(1.0)).pow(2)
            sin(2 * PI * f * t) * 0.85 * (1 - t / 0.62).pow(2)
        }
        // Logotip akkordi (E-dur), aks-sado bilan
        listOf(164.81, 246.94, 329.63, 415.3, 493.88, 659.25).forEachIndexed { i, f ->
            for (echo in 0..2) add(impact + i * 0.035 + echo * 0.19, 1.7) { t ->
                val env = (1 - t / 1.7).pow(3) * minOf(1.0, t / 0.02)
                sin(2 * PI * f * t) * 0.13 * env * 0.32.pow(echo)
            }
        }
        val peak = mix.maxOf { kotlin.math.abs(it) }.coerceAtLeast(1f)
        val gain = (0.85f / peak)
        return ShortArray(total) { i ->
            val fade = if (i > total - RATE / 4) (total - i).toFloat() / (RATE / 4) else 1f
            (mix[i] * gain * fade * Short.MAX_VALUE).toInt().toShort()
        }
    }

    companion object { const val RATE = 44100 }
}
