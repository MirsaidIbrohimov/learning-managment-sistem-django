package uz.itcacademy.parent.screens

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.RepeatMode
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
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import uz.itcacademy.parent.*
import uz.itcacademy.parent.ui.*

private class Step(val icon: ImageVector, val title: String, val text: String, val tab: Int = -1, val bullets: List<Pair<ImageVector, String>> = emptyList())

private val STEPS = listOf(
    Step(Icons.Rounded.FamilyRestroom, "Xuş kelibsiz!", "ITC Ota Ona orqali farzandingizning öqişi, davomati, baholari va tölovlarini istalgan payt kuzatasiz. Keling, qisqaça tanişib çiqamiz."),
    Step(Icons.Rounded.Home, "Bosh sahifa", "Eng muhimi bir joyda: umumiy özlaştiriş, e'tibor beriş kerak bölgan holatlar va keyingi dars vaqti.", 0, listOf(
        Icons.Rounded.DonutLarge to "Özlaştiriş foizi va test, davomat, vazifa körsatkiçlari",
        Icons.Rounded.WarningAmber to "Ogohlantirişlar: tölov, qoldirilgan dars, past baho",
        Icons.Rounded.BarChart to "Haftalik faollik grafigi",
    )),
    Step(Icons.Rounded.SwitchAccount, "Farzandni tanlaş", "Bir neçta farzandingiz bölsa, sahifa tepasidagi ismlardan birini bosing — barça bölimlar şu farzand böyiça körsatiladi."),
    Step(Icons.Rounded.MenuBook, "Öqiş", "Kurslar, darslar, uy vazifalari va test natijalari. Har bir dars bajarilgan-bajarilmagani belgilangan.", 1, listOf(
        Icons.Rounded.PlayLesson to "Darslar: qaysi biri körilgan, qaysi biri qolgan",
        Icons.Rounded.Assignment to "Vazifalar: muddat, baho va ustoz izohi",
        Icons.Rounded.Quiz to "Testlar: ball, ötdi yoki ötmadi",
    )),
    Step(Icons.Rounded.EventAvailable, "Davomat va jadval", "Darsga kelgan, keçikkan yoki kelmagan kunlar kalendarda. Haftalik dars jadvali ham şu yerda.", 2),
    Step(Icons.Rounded.AccountBalanceWallet, "Tölov", "Balans, oylik tölov va keyingi tölov sanasi. \"Tölaş\" tugmasi orqali onlayn tölov qilasiz.", 3, listOf(
        Icons.Rounded.Lock to "Tölov xavfsiz sahifada, tizim brauzerida oçiladi",
        Icons.Rounded.ReceiptLong to "Barça tölovlar tarixi",
    )),
    Step(Icons.Rounded.GridView, "Yana", "Qolgan bölimlar: yutuqlar va sertifikatlar, kutubxona kitoblari, öquv markazi bilan yozişma, profil va sozlamalar.", 4),
    Step(Icons.Rounded.NotificationsActive, "Bildirişnomalar", "Farzandingiz test topşirsa, vazifasi baholansa, darsga kelmasa yoki tölov muddati yaqinlaşsa — telefoningizga xabar keladi."),
    Step(Icons.Rounded.Shield, "Xavfsizlik", "Ilova PIN-kod bilan himoyalangan, ekran rasmi olinmaydi. Qöllanmani istalgan payt \"Yana → Qöllanma\" böliminidan qayta oçasiz."),
)

@Composable
fun TourOverlay(onDone: () -> Unit) {
    var i by remember { mutableIntStateOf(0) }
    var dir by remember { mutableIntStateOf(1) }
    val last = i == STEPS.lastIndex
    fun next() { if (last) onDone() else { dir = 1; i++ } }
    fun prev() { if (i > 0) { dir = -1; i-- } }
    BackHandler { if (i > 0) prev() else onDone() }
    val p = pal

    Box(
        Modifier.fillMaxSize().background(Color(0xEB050412))
            .clickable(remember { MutableInteractionSource() }, null) { }
            .pointerInput(Unit) {
                var total = 0f
                detectHorizontalDragGestures(onDragEnd = {
                    if (total < -80) next() else if (total > 80) prev()
                    total = 0f
                }) { _, d -> total += d }
            },
    ) {
        Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().padding(18.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Txt("${i + 1} / ${STEPS.size}", size = 13.sp, color = Color.White.copy(alpha = .7f), weight = FontWeight.SemiBold)
                Spacer(Modifier.weight(1f))
                if (!last) Txt("Ötkazib yuboriş", Modifier.press(onClick = onDone).padding(8.dp), 14.sp, FontWeight.SemiBold, Color.White.copy(alpha = .85f))
            }
            Spacer(Modifier.weight(1f))
            AnimatedContent(i, transitionSpec = {
                if (!motionOn) fadeIn(tween(0)) togetherWith fadeOut(tween(0))
                else (slideInHorizontally(spring(.8f, Spring.StiffnessMediumLow)) { it / 2 * dir } + fadeIn()) togetherWith
                    (slideOutHorizontally(tween(200)) { -it / 3 * dir } + fadeOut(tween(150)))
            }, label = "tour") { idx ->
                val s = STEPS[idx]
                Column(
                    Modifier.fillMaxWidth().glassBlur(RoundedCornerShape(32.dp), if (p.dark) Color(0xE61A1A28) else Color(0xF2FFFFFF)).padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    TourIcon(s.icon)
                    Spacer(Modifier.height(20.dp))
                    Txt(s.title, size = 23.sp, weight = FontWeight.Bold, align = TextAlign.Center)
                    Spacer(Modifier.height(8.dp))
                    Txt(s.text, size = 15.sp, color = p.text2, align = TextAlign.Center)
                    if (s.bullets.isNotEmpty()) {
                        Spacer(Modifier.height(16.dp))
                        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            s.bullets.forEachIndexed { k, (ic, tx) ->
                                Row(Modifier.reveal(k + 1), verticalAlignment = Alignment.CenterVertically) {
                                    IcoBox(ic, p.a1, 34.dp)
                                    Spacer(Modifier.width(12.dp))
                                    Txt(tx, size = 14.sp, modifier = Modifier.weight(1f))
                                }
                            }
                        }
                    }
                    if (s.tab >= 0) {
                        Spacer(Modifier.height(20.dp))
                        MiniTabBar(s.tab)
                    }
                }
            }
            Spacer(Modifier.weight(1f))
            Row(Modifier.fillMaxWidth().padding(vertical = 16.dp), horizontalArrangement = Arrangement.Center) {
                STEPS.indices.forEach { k ->
                    val w by animateDpAsState(if (k == i) 22.dp else 7.dp, spring(.7f, Spring.StiffnessMediumLow), label = "dot")
                    Box(Modifier.padding(horizontal = 3.dp).height(7.dp).width(w).clip(CircleShape)
                        .background(if (k == i) Color.White else Color.White.copy(alpha = .35f)))
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                if (i > 0) Btn("Orqaga", Modifier.weight(1f), icon = Icons.Rounded.ChevronLeft) { prev() }
                Btn(if (last) "Boşlaş" else "Keyingi", Modifier.weight(if (i > 0) 1.4f else 1f), BtnKind.Primary,
                    if (last) Icons.Rounded.Check else Icons.Rounded.ChevronRight) { next() }
            }
        }
    }
}

/** Sekin tebranuvchi katta ikonka. */
@Composable
private fun TourIcon(icon: ImageVector) {
    val p = pal
    val tr = rememberInfiniteTransition(label = "ti")
    val y by tr.animateFloat(0f, if (motionOn) -8f else 0f, infiniteRepeatable(tween(1600), RepeatMode.Reverse), label = "y")
    val glow by tr.animateFloat(.35f, if (motionOn) .7f else .35f, infiniteRepeatable(tween(1600), RepeatMode.Reverse), label = "g")
    Box(Modifier.size(120.dp), contentAlignment = Alignment.Center) {
        Box(Modifier.size(120.dp).graphicsLayer { alpha = glow }.clip(CircleShape)
            .background(Brush.radialGradient(listOf(p.a1.copy(alpha = .6f), Color.Transparent))))
        Box(
            Modifier.graphicsLayer { translationY = y }.size(84.dp).clip(RoundedCornerShape(28.dp))
                .background(Brush.linearGradient(listOf(p.a1, p.a2))),
            contentAlignment = Alignment.Center,
        ) { Icon(icon, null, Modifier.size(42.dp), Color.White) }
    }
}

/** Pastki panelning kichik nusxasi: kerakli tugma yorug' halqa bilan ko'rsatiladi. */
@Composable
private fun MiniTabBar(active: Int) {
    val p = pal
    val tr = rememberInfiniteTransition(label = "mt")
    val ring by tr.animateFloat(1f, if (motionOn) 1.25f else 1f, infiniteRepeatable(tween(900), RepeatMode.Reverse), label = "r")
    Row(
        Modifier.fillMaxWidth().height(58.dp).clip(RoundedCornerShape(24.dp)).background(p.surface2).border(1.dp, p.border, RoundedCornerShape(24.dp)),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        TABS.forEachIndexed { k, tab ->
            val on = k == active
            Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                Box(contentAlignment = Alignment.Center) {
                    if (on) Box(Modifier.size(38.dp).graphicsLayer { scaleX = ring; scaleY = ring; alpha = 2f - ring * 1.2f }
                        .clip(CircleShape).border(2.dp, p.a1, CircleShape))
                    Icon(tab.icon, null, Modifier.size(21.dp), if (on) p.a1 else p.muted)
                }
                Txt(tab.label.substringBefore(' '), size = 9.5.sp, color = if (on) p.text else p.muted, lines = 1)
            }
        }
    }
}
