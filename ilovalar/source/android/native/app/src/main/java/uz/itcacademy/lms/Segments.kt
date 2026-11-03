package uz.itcacademy.lms

/**
 * Ko'rilgan oraliqlar: [boshlanish, tugash] soniyalarda, tartiblangan.
 * Saytdagi VideoTimer bilan bir xil hisob: server ham shu oraliqlarni birlashtiradi.
 */
data class Seg(val start: Double, val end: Double)

object Segments {
    fun normalize(list: List<Seg>): List<Seg> {
        val out = ArrayList<Seg>()
        list.filter { it.start.isFinite() && it.end.isFinite() && it.end > it.start && it.start >= 0 }
            .sortedBy { it.start }
            .forEach { s ->
                val last = out.lastOrNull()
                if (last != null && s.start <= last.end + 0.25) out[out.lastIndex] = Seg(last.start, maxOf(last.end, s.end))
                else out += s
            }
        return out
    }

    fun union(a: List<Seg>, b: List<Seg>) = normalize(a + b)

    /** a dan b ni ayiradi. */
    fun subtract(a: List<Seg>, b: List<Seg>): List<Seg> {
        val out = ArrayList<Seg>()
        a.forEach { seg ->
            var parts = listOf(seg)
            b.forEach { cut ->
                parts = parts.flatMap { p ->
                    if (cut.end <= p.start || cut.start >= p.end) listOf(p)
                    else buildList {
                        if (cut.start > p.start) add(Seg(p.start, cut.start))
                        if (cut.end < p.end) add(Seg(cut.end, p.end))
                    }
                }
            }
            out += parts.filter { it.end - it.start > 0.01 }
        }
        return normalize(out)
    }

    fun total(list: List<Seg>, cap: Double = 0.0): Double =
        list.sumOf { s -> maxOf(0.0, (if (cap > 0) minOf(s.end, cap) else s.end) - s.start) }

    /** Ikki o'qish orasidagi siljish haqiqiy ijromi. Sakrash va uzoq to'xtash sanalmaydi. */
    fun isRealPlayback(dPos: Double, dWall: Double, maxRate: Double = 2.25): Boolean =
        dPos > 0 && dWall > 0 && dWall < 6 && dPos <= dWall * maxRate + 0.6
}
