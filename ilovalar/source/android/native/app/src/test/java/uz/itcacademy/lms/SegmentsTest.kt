package uz.itcacademy.lms

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SegmentsTest {
    @Test fun mergesOverlappingAndNearby() {
        val r = Segments.normalize(listOf(Seg(10.0, 20.0), Seg(0.0, 5.0), Seg(5.1, 8.0), Seg(19.0, 25.0)))
        assertEquals(listOf(Seg(0.0, 8.0), Seg(10.0, 25.0)), r)
    }

    @Test fun dropsInvalid() {
        assertEquals(emptyList<Seg>(), Segments.normalize(listOf(Seg(5.0, 5.0), Seg(9.0, 3.0), Seg(-1.0, 4.0), Seg(Double.NaN, 4.0))))
    }

    @Test fun subtractKeepsOnlyUncovered() {
        val r = Segments.subtract(listOf(Seg(0.0, 100.0)), listOf(Seg(10.0, 20.0), Seg(50.0, 60.0)))
        assertEquals(listOf(Seg(0.0, 10.0), Seg(20.0, 50.0), Seg(60.0, 100.0)), r)
    }

    @Test fun subtractEverythingLeavesNothing() {
        assertEquals(emptyList<Seg>(), Segments.subtract(listOf(Seg(5.0, 6.0)), listOf(Seg(0.0, 10.0))))
    }

    @Test fun totalRespectsCap() {
        val l = listOf(Seg(0.0, 10.0), Seg(20.0, 40.0))
        assertEquals(30.0, Segments.total(l), 0.001)
        assertEquals(15.0, Segments.total(l, 25.0), 0.001)
    }

    @Test fun normalPlaybackCounts() {
        assertTrue(Segments.isRealPlayback(1.0, 1.0))
        assertTrue(Segments.isRealPlayback(2.0, 1.0))
    }

    @Test fun seekAndStallDoNotCount() {
        assertFalse(Segments.isRealPlayback(120.0, 1.0))
        assertFalse(Segments.isRealPlayback(-30.0, 1.0))
        assertFalse(Segments.isRealPlayback(0.0, 1.0))
        assertFalse(Segments.isRealPlayback(5.0, 8.0))
    }
}
