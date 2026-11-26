package io.github.satoshimiyasaka.fieldmark

import org.json.JSONObject
import java.util.Locale

/** Pure logic: compass points, tide highs and lows, and reading Open-Meteo's answers. */
object Field {
    private val POINTS = arrayOf(
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    )

    /** The 16-point compass name of a direction in degrees. */
    fun compassPoint(degrees: Double): String {
        val d = ((degrees % 360) + 360) % 360
        return POINTS[((d / 22.5) + 0.5).toInt() % 16]
    }

    data class Extreme(val time: Long, val height: Double, val high: Boolean)

    /**
     * High and low waters of an hourly series. Each turn is moved off the hour
     * by a parabola through it and its two neighbours, so the times are not
     * all on the hour.
     */
    fun extremes(times: LongArray, heights: DoubleArray): List<Extreme> {
        val out = ArrayList<Extreme>()
        for (i in 1 until heights.size - 1) {
            val a = heights[i - 1]
            val b = heights[i]
            val c = heights[i + 1]
            if (a.isNaN() || b.isNaN() || c.isNaN()) continue
            val high = b > a && b >= c
            val low = b < a && b <= c
            if (!high && !low) continue
            val curvature = a - 2 * b + c
            val offset = if (curvature != 0.0) (0.5 * (a - c) / curvature).coerceIn(-0.5, 0.5) else 0.0
            val step = times[i + 1] - times[i]
            out += Extreme(times[i] + (offset * step).toLong(), b - 0.25 * (a - c) * offset, high)
        }
        return out
    }

    fun next(extremes: List<Extreme>, now: Long, high: Boolean): Extreme? =
        extremes.firstOrNull { it.time > now && it.high == high }

    class Forecast(
        val windDirection: Double,
        val windSpeed: Double,
        val windAt: Long,
        val sunrise: LongArray,
        val sunset: LongArray,
    )

    class Marine(val times: LongArray, val heights: DoubleArray)

    fun forecastUrl(lat: Double, lon: Double): String = String.format(
        Locale.US,
        "https://api.open-meteo.com/v1/forecast?latitude=%.3f&longitude=%.3f" +
            "&current=wind_speed_10m,wind_direction_10m&daily=sunrise,sunset" +
            "&wind_speed_unit=ms&timeformat=unixtime&timezone=auto&forecast_days=3",
        lat, lon,
    )

    fun marineUrl(lat: Double, lon: Double): String = String.format(
        Locale.US,
        "https://marine-api.open-meteo.com/v1/marine?latitude=%.3f&longitude=%.3f" +
            "&hourly=sea_level_height_msl&timeformat=unixtime&timezone=auto&forecast_days=3",
        lat, lon,
    )

    /** Times come as Unix seconds (timeformat=unixtime); they are kept in milliseconds. */
    fun parseForecast(json: String): Forecast {
        val root = JSONObject(json)
        val current = root.getJSONObject("current")
        val daily = root.getJSONObject("daily")
        val rise = daily.getJSONArray("sunrise")
        val set = daily.getJSONArray("sunset")
        return Forecast(
            windDirection = current.getDouble("wind_direction_10m"),
            windSpeed = current.getDouble("wind_speed_10m"),
            windAt = current.getLong("time") * 1000,
            sunrise = LongArray(rise.length()) { rise.getLong(it) * 1000 },
            sunset = LongArray(set.length()) { set.getLong(it) * 1000 },
        )
    }

    /** Null away from the sea, where Open-Meteo has no sea level. */
    fun parseMarine(json: String): Marine? {
        val hourly = JSONObject(json).optJSONObject("hourly") ?: return null
        val time = hourly.getJSONArray("time")
        val level = hourly.optJSONArray("sea_level_height_msl") ?: return null
        val heights = DoubleArray(level.length()) { if (level.isNull(it)) Double.NaN else level.getDouble(it) }
        if (heights.all { it.isNaN() }) return null
        return Marine(LongArray(time.length()) { time.getLong(it) * 1000 }, heights)
    }

    /** Distance in km, good enough to tell whether we have moved. */
    fun distanceKm(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
        val dLat = Math.toRadians(lat2 - lat1)
        val dLon = Math.toRadians(lon2 - lon1) * Math.cos(Math.toRadians((lat1 + lat2) / 2))
        return 6371.0 * Math.sqrt(dLat * dLat + dLon * dLon)
    }
}
