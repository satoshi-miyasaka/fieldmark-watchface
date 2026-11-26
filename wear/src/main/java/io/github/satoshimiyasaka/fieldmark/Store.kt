package io.github.satoshimiyasaka.fieldmark

import android.content.ComponentName
import android.content.Context
import androidx.wear.watchface.complications.datasource.ComplicationDataSourceUpdateRequester

/** What the last update found, kept on the watch. Times are epoch milliseconds. */
class Snapshot(
    val lat: Double,
    val lon: Double,
    val locatedAt: Long,
    val windDirection: Double,
    val windSpeed: Double,
    val windAt: Long,
    val sunrise: LongArray,
    val sunset: LongArray,
    val tideTimes: LongArray,
    val tideHeights: DoubleArray,
    val marineAt: Long,
    val marineLat: Double,
    val marineLon: Double,
    val updatedAt: Long,
    val status: String,
) {
    val hasLocation get() = locatedAt > 0
    val hasTide get() = tideTimes.isNotEmpty()
}

object Store {
    private fun prefs(context: Context) = context.getSharedPreferences("fieldmark", Context.MODE_PRIVATE)

    private fun longs(text: String?): LongArray =
        text.orEmpty().split(',').filter { it.isNotEmpty() }.map { it.toLong() }.toLongArray()

    private fun doubles(text: String?): DoubleArray =
        text.orEmpty().split(',').filter { it.isNotEmpty() }.map { it.toDouble() }.toDoubleArray()

    private fun android.content.SharedPreferences.double(key: String): Double =
        java.lang.Double.longBitsToDouble(getLong(key, java.lang.Double.doubleToRawLongBits(Double.NaN)))

    private fun android.content.SharedPreferences.Editor.putDouble(key: String, value: Double) =
        putLong(key, java.lang.Double.doubleToRawLongBits(value))

    fun load(context: Context): Snapshot {
        val p = prefs(context)
        return Snapshot(
            lat = p.double("lat"),
            lon = p.double("lon"),
            locatedAt = p.getLong("located_at", 0),
            windDirection = p.double("wind_dir"),
            windSpeed = p.double("wind_speed"),
            windAt = p.getLong("wind_at", 0),
            sunrise = longs(p.getString("sunrise", "")),
            sunset = longs(p.getString("sunset", "")),
            tideTimes = longs(p.getString("tide_times", "")),
            tideHeights = doubles(p.getString("tide_heights", "")),
            marineAt = p.getLong("marine_at", 0),
            marineLat = p.double("marine_lat"),
            marineLon = p.double("marine_lon"),
            updatedAt = p.getLong("updated_at", 0),
            status = p.getString("status", "").orEmpty(),
        )
    }

    fun saveLocation(context: Context, lat: Double, lon: Double, at: Long) {
        prefs(context).edit().putDouble("lat", lat).putDouble("lon", lon).putLong("located_at", at).apply()
    }

    fun saveForecast(context: Context, f: Field.Forecast) {
        prefs(context).edit()
            .putDouble("wind_dir", f.windDirection)
            .putDouble("wind_speed", f.windSpeed)
            .putLong("wind_at", f.windAt)
            .putString("sunrise", f.sunrise.joinToString(","))
            .putString("sunset", f.sunset.joinToString(","))
            .apply()
    }

    /** marine is null away from the sea: the tide is cleared. */
    fun saveMarine(context: Context, marine: Field.Marine?, lat: Double, lon: Double, at: Long) {
        prefs(context).edit()
            .putString("tide_times", marine?.times?.joinToString(",").orEmpty())
            .putString("tide_heights", marine?.heights?.joinToString(",").orEmpty())
            .putLong("marine_at", at)
            .putDouble("marine_lat", lat)
            .putDouble("marine_lon", lon)
            .apply()
    }

    fun saveStatus(context: Context, status: String, at: Long) {
        prefs(context).edit().putString("status", status).putLong("updated_at", at).apply()
    }

    fun refreshWatchFace(context: Context) {
        for (source in listOf(
            WindDataSource::class.java,
            SunDataSource::class.java,
            TideCurveADataSource::class.java,
            TideCurveBDataSource::class.java,
            TideTimesDataSource::class.java,
        )) {
            ComplicationDataSourceUpdateRequester
                .create(context, ComponentName(context, source))
                .requestUpdateAll()
        }
    }
}
