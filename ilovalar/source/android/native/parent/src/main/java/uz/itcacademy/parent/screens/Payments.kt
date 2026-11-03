package uz.itcacademy.parent.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
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

@Composable
fun PaymentsScreen() {
    val load = rememberChildLoad("payments/")
    Refreshable({ load.retry() }) {
        Page {
            TabHeader("Tölov", AppState.child?.str("name"))
            if (AppState.children.isEmpty()) { NoChild(); return@Page }
            val d = load.data
            when {
                d == null && load.error != null -> ErrorState(load.error, load.retry)
                d == null -> SkeletonList(4, 110.dp)
                else -> PaymentsBody(d)
            }
        }
    }
}

@Composable
private fun PaymentsBody(d: JSONObject) {
    val p = pal
    val ctx = LocalContext.current
    val pay = d.obj("payment") ?: JSONObject()
    val (c, title, sub) = paymentState(pay)
    val contract = pay.bool("is_contract")

    // Holat kartasi
    Column(
        Modifier.reveal(0).fillMaxWidth().clip(RoundedCornerShape(26.dp))
            .background(Brush.linearGradient(listOf(c.copy(alpha = .30f), c.copy(alpha = .08f))))
            .padding(20.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IcoBox(Icons.Rounded.AccountBalanceWallet, c, 48.dp)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Txt(title, size = 18.sp, weight = FontWeight.Bold)
                if (sub.isNotEmpty()) Muted(sub, translate = false)
            }
        }
        if (!contract) {
            Spacer(Modifier.height(18.dp))
            Muted("Balans")
            Row(verticalAlignment = Alignment.Bottom) {
                CountUp(pay.intOrNull("balance") ?: 0, 32.sp)
                Spacer(Modifier.width(6.dp))
                Txt("söm", Modifier.padding(bottom = 5.dp), 15.sp, color = p.text2)
            }
            pay.intOrNull("months_covered")?.takeIf { it > 0 }?.let { Muted("Balans taxminan $it oyga yetadi") }
        }
    }

    Row(Modifier.reveal(1), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Stat(Icons.Rounded.CalendarMonth, p.blue, pay.intOrNull("fee")?.let { num(it) } ?: "—", "Oylik tölov, söm", Modifier.weight(1f))
        Stat(Icons.Rounded.Event, p.a1, pay.strOrNull("next_date")?.let { dateText(it, false) } ?: "—", "Keyingi tölov", Modifier.weight(1f))
    }

    if (!contract) {
        if (d.bool("can_pay_online")) Btn("Onlayn tölaş", Modifier.reveal(2).fillMaxWidth().height(54.dp), BtnKind.Primary, Icons.Rounded.CreditCard) {
            paySheet(ctx, d)
        } else Row(
            Modifier.reveal(2).fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(p.surface2).padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Rounded.Info, null, Modifier.size(20.dp), p.blue)
            Spacer(Modifier.width(10.dp))
            Muted("Onlayn tölov hozirça mavjud emas. Tölov böyiça öquv markazi administratoriga murojaat qiling.", size = 13.5.sp)
        }
    }

    val records = pay.list("records")
    GlassCard(Modifier.reveal(3)) {
        SectionTitle("Tölovlar tarixi", Icons.Rounded.ReceiptLong)
        if (records.isEmpty()) Muted("Hali tölov yozuvlari yöq")
        records.forEachIndexed { i, r ->
            if (i > 0) Hairline()
            val paid = r.bool("is_paid")
            val debt = r.int("debt")
            Row2(
                "${r.str("month_name")} ${r.int("year")}",
                listOfNotNull(
                    r.strOrNull("paid_date")?.let { "Tölangan: ${dateText(it)}" },
                    if (!paid && debt > 0) "Qarz: ${som(debt)}" else null,
                    r.str("notes").takeIf { it.isNotEmpty() },
                ).joinToString(" · "),
                translate = false,
                leading = { IcoBox(if (paid) Icons.Rounded.CheckCircle else Icons.Rounded.Schedule, if (paid) p.green else p.amber, 36.dp) },
                trailing = {
                    Column(horizontalAlignment = Alignment.End) {
                        Txt(num(if (paid) r.int("paid_amount") else r.int("amount")), weight = FontWeight.Bold)
                        Muted("söm", size = 11.sp)
                    }
                },
            )
        }
    }
    Row(Modifier.padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Rounded.Lock, null, Modifier.size(15.dp), p.muted)
        Spacer(Modifier.width(6.dp))
        Muted("Tölov tasdiqlangaç balans avtomatik yangilanadi va sizga bildirişnoma keladi.", size = 12.sp)
    }
}

/** Onlayn to'lov: saytdagi xavfsiz sahifa tizim brauzerida bir martalik havola bilan ochiladi. */
private fun paySheet(ctx: android.content.Context, d: JSONObject) = Sheets.show { close ->
    val p = pal
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    val childId = AppState.child?.int("id") ?: 0
    IcoBox(Icons.Rounded.CreditCard, p.a1, 48.dp)
    Spacer(Modifier.height(12.dp))
    Txt("Onlayn tölov", size = 20.sp, weight = FontWeight.Bold)
    Muted("${AppState.child?.str("name").orEmpty()} uçun tölov sahifasi xavfsiz brauzerda oçiladi. U yerda summani tanlab, karta orqali tölaysiz.",
        Modifier.padding(top = 6.dp, bottom = 14.dp), 14.sp)
    val presets = d.list("presets")
    if (presets.isNotEmpty()) {
        Muted("Tavsiya etilgan summalar")
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            presets.take(4).forEach { pr ->
                Column(Modifier.weight(1f).clip(RoundedCornerShape(14.dp)).background(p.surface2).padding(vertical = 10.dp),
                    horizontalAlignment = Alignment.CenterHorizontally) {
                    Txt("${pr.int("months")} oy", size = 12.sp, color = p.text2)
                    Txt(num(pr.int("amount")), size = 13.sp, weight = FontWeight.Bold, lines = 1)
                }
            }
        }
        Spacer(Modifier.height(16.dp))
    }
    Btn("Tölov sahifasini oçiş", Modifier.fillMaxWidth(), BtnKind.Primary, Icons.Rounded.OpenInBrowser, busy = busy) {
        busy = true
        scope.launch {
            try {
                val r = Api.post("children/$childId/pay/")
                val url = Api.siteUrl(r.optString("url"))
                if (url != null) { openBrowser(ctx, url); close() } else Toasts.show("Havola olinmadi", "err")
            } catch (e: ApiError) { Toasts.show(e.message.orEmpty(), "err") }
            busy = false
        }
    }
    Spacer(Modifier.height(8.dp))
    Btn("Bekor qiliş", Modifier.fillMaxWidth(), BtnKind.Ghost, onClick = close)
}
