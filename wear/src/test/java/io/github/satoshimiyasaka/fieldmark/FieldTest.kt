package io.github.satoshimiyasaka.fieldmark

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class FieldTest {

    @Test
    fun compassPoints() {
        assertEquals("N", Field.compassPoint(0.0))
        assertEquals("N", Field.compassPoint(359.0))
        assertEquals("NW", Field.compassPoint(315.0))
        assertEquals("SSW", Field.compassPoint(200.0))
        assertEquals("E", Field.compassPoint(-270.0))
    }

    @Test
    fun extremesOfASemidiurnalTide() {
        val hour = 3600_000L
        val times = LongArray(48) { it * hour }
        // High water at 5.2 h, then every 12.42 h.
        val heights = DoubleArray(48) { Math.cos(2 * Math.PI * (it - 5.2) / 12.42) }
        val e = Field.extremes(times, heights)
        val highs = e.filter { it.high }
        val lows = e.filter { !it.high }
        assertEquals(4, highs.size)
        assertEquals(3, lows.size)
        assertTrue(Math.abs(highs[0].time - (5.2 * hour).toLong()) < 10 * 60_000)
        assertTrue(Math.abs(lows[0].time - ((5.2 + 6.21) * hour).toLong()) < 10 * 60_000)
        val next = Field.next(e, (6 * hour), high = true)!!
        assertTrue(Math.abs(next.time - ((5.2 + 12.42) * hour).toLong()) < 10 * 60_000)
    }

    @Test
    fun extremesSkipGaps() {
        val times = LongArray(5) { it * 3600_000L }
        val heights = doubleArrayOf(0.0, 1.0, Double.NaN, 1.0, 0.0)
        assertTrue(Field.extremes(times, heights).isEmpty())
    }

    @Test
    fun readsForecast() {
        val json = """{"utc_offset_seconds":32400,
            "current":{"time":1795741200,"interval":900,"wind_speed_10m":3.2,"wind_direction_10m":315},
            "daily":{"time":[1795705200,1795791600],"sunrise":[1795727580,1795814040],
            "sunset":[1795764660,1795851020]}}"""
        val f = Field.parseForecast(json)
        assertEquals(315.0, f.windDirection, 0.0)
        assertEquals(3.2, f.windSpeed, 0.0)
        assertEquals(1795741200_000L, f.windAt)
        assertEquals(2, f.sunrise.size)
        assertEquals(1795764660_000L, f.sunset[0])
    }

    @Test
    fun readsMarineAndInland() {
        val sea = """{"hourly":{"time":[0,3600,7200],"sea_level_height_msl":[0.1,null,0.3]}}"""
        val m = Field.parseMarine(sea)!!
        assertEquals(3, m.times.size)
        assertTrue(m.heights[1].isNaN())
        assertEquals(7200_000L, m.times[2])
        val inland = """{"hourly":{"time":[0,3600],"sea_level_height_msl":[null,null]}}"""
        assertNull(Field.parseMarine(inland))
    }

    @Test
    fun tideCurveAndPacking() {
        val hour = 3600_000L
        val times = LongArray(30) { it * hour }
        val heights = DoubleArray(30) { it.toDouble() }  // rising steadily
        val curve = Field.tideCurve(times, heights, 0)!!
        assertEquals(13, curve.size)
        assertEquals(0, curve[0])
        assertEquals(63, curve[12])
        assertTrue((0 until 12).all { curve[it] <= curve[it + 1] })
        // Not covering 24 h is no curve.
        assertNull(Field.tideCurve(times, heights, 10 * hour))
        // Packing, read back the way the face reads it: floor(x / 64^k) % 64.
        val packed = Field.pack(intArrayOf(1, 2, 3, 63), 0, 4)
        assertEquals(1 + 2 * 64 + 3 * 4096 + 63 * 262144, packed)
        assertTrue(packed < (1 shl 24))  // exact in a float
        assertEquals(63, (packed / 262144) % 64)
        assertEquals(0, Field.pack(intArrayOf(5), 1, 0))
    }

    @Test
    fun distance() {
        // Tokyo to Yokohama, about 27 km.
        val d = Field.distanceKm(35.68, 139.77, 35.44, 139.64)
        assertTrue(d in 25.0..32.0)
    }
}
