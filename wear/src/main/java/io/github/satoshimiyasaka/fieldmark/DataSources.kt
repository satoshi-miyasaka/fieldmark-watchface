package io.github.satoshimiyasaka.fieldmark

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.drawable.Icon
import androidx.wear.watchface.complications.data.ComplicationData
import androidx.wear.watchface.complications.data.ComplicationType
import androidx.wear.watchface.complications.data.NoDataComplicationData
import androidx.wear.watchface.complications.data.PhotoImageComplicationData
import androidx.wear.watchface.complications.data.PlainComplicationText
import androidx.wear.watchface.complications.data.RangedValueComplicationData
import androidx.wear.watchface.complications.data.ShortTextComplicationData
import androidx.wear.watchface.complications.datasource.ComplicationDataSourceService
import androidx.wear.watchface.complications.datasource.ComplicationDataSourceService.ComplicationRequestListener
import androidx.wear.watchface.complications.datasource.ComplicationDataTimeline
import androidx.wear.watchface.complications.datasource.ComplicationRequest
import androidx.wear.watchface.complications.datasource.TimeInterval
import androidx.wear.watchface.complications.datasource.TimelineEntry
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private fun plain(text: String) = PlainComplicationText.Builder(text).build()

private val HH_MM: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")

private fun clock(time: Long, zone: ZoneId) = HH_MM.format(Instant.ofEpochMilli(time).atZone(zone))

private fun startOfDay(date: LocalDate, zone: ZoneId) = date.atStartOfDay(zone).toInstant().toEpochMilli()

/** Base for the four sources: answers only its own type and schedules updates once it is in use. */
abstract class FieldDataSource(private val type: ComplicationType) : ComplicationDataSourceService() {

    abstract fun answer(s: Snapshot, now: Long, zone: ZoneId, listener: ComplicationRequestListener)

    abstract fun preview(): ComplicationData

    override fun onComplicationActivated(complicationInstanceId: Int, type: ComplicationType) {
        Updater.schedule(this)
    }

    override fun onComplicationRequest(request: ComplicationRequest, listener: ComplicationRequestListener) {
        if (request.complicationType != type) {
            listener.onComplicationData(null)
            return
        }
        answer(Store.load(this), System.currentTimeMillis(), ZoneId.systemDefault(), listener)
    }

    override fun getPreviewData(type: ComplicationType): ComplicationData? =
        if (type == this.type) preview() else null
}

/** RANGED_VALUE: value = where the wind comes from in degrees, title = compass point, text = m/s. */
class WindDataSource : FieldDataSource(ComplicationType.RANGED_VALUE) {

    override fun answer(s: Snapshot, now: Long, zone: ZoneId, listener: ComplicationRequestListener) {
        val fresh = s.windAt > 0 && now - s.windAt < STALE && !s.windDirection.isNaN()
        listener.onComplicationData(if (fresh) wind(s.windDirection, s.windSpeed) else NoDataComplicationData())
    }

    override fun preview() = wind(315.0, 3.2)

    private fun wind(direction: Double, speed: Double): ComplicationData {
        val point = Field.compassPoint(direction)
        val speedText = String.format(java.util.Locale.US, "%.1f", speed)
        return RangedValueComplicationData.Builder(
            direction.toFloat().coerceIn(0f, 360f), 0f, 360f, plain("風 $point $speedText m/s"),
        ).setTitle(plain(point)).setText(plain(speedText)).build()
    }

    private companion object {
        const val STALE = 3 * 60 * 60 * 1000L
    }
}

/**
 * RANGED_VALUE: min = sunrise and max = sunset in minutes after midnight,
 * text = sunrise, title = sunset. A timeline switches to tomorrow at midnight.
 */
class SunDataSource : FieldDataSource(ComplicationType.RANGED_VALUE) {

    override fun answer(s: Snapshot, now: Long, zone: ZoneId, listener: ComplicationRequestListener) {
        val today = Instant.ofEpochMilli(now).atZone(zone).toLocalDate()
        val days = (0..1).map { today.plusDays(it.toLong()) }
        val data = days.map { day(s, it, zone) }
        if (data[0] == null) {
            listener.onComplicationData(NoDataComplicationData())
            return
        }
        val entries = ArrayList<TimelineEntry>()
        data[1]?.let {
            val start = Instant.ofEpochMilli(startOfDay(days[1], zone))
            entries += TimelineEntry(TimeInterval(start, start.plusSeconds(24 * 3600)), it)
        }
        listener.onComplicationDataTimeline(ComplicationDataTimeline(data[0]!!, entries))
    }

    override fun preview() = sun(6 * 60 + 13, 16 * 60 + 38, "06:13", "16:38")

    private fun day(s: Snapshot, date: LocalDate, zone: ZoneId): ComplicationData? {
        val from = startOfDay(date, zone)
        val to = startOfDay(date.plusDays(1), zone)
        val rise = s.sunrise.firstOrNull { it in from until to } ?: return null
        val set = s.sunset.firstOrNull { it in from until to } ?: return null
        if (set <= rise) return null
        val minutes = { t: Long -> ((t - from) / 60_000).toInt() }
        return sun(minutes(rise), minutes(set), clock(rise, zone), clock(set, zone))
    }

    private fun sun(rise: Int, set: Int, riseText: String, setText: String): ComplicationData =
        RangedValueComplicationData.Builder(
            rise.toFloat(), rise.toFloat(), set.toFloat(), plain("日の出 $riseText 日の入り $setText"),
        ).setText(plain(riseText)).setTitle(plain(setText)).build()
}

/** SHORT_TEXT: text = next high water, title = next low water, changing at each turn of the tide. */
class TideTimesDataSource : FieldDataSource(ComplicationType.SHORT_TEXT) {

    override fun answer(s: Snapshot, now: Long, zone: ZoneId, listener: ComplicationRequestListener) {
        val extremes = Field.extremes(s.tideTimes, s.tideHeights)
        val first = times(extremes, now, zone)
        if (first == null) {
            listener.onComplicationData(NoDataComplicationData())
            return
        }
        // A new answer from each turn of the tide in the next day.
        val turns = extremes.map { it.time }.filter { it > now && it < now + 24 * 3600_000L }
        val entries = turns.mapIndexedNotNull { i, t ->
            val end = turns.getOrElse(i + 1) { now + 24 * 3600_000L }
            times(extremes, t, zone)?.let {
                TimelineEntry(TimeInterval(Instant.ofEpochMilli(t), Instant.ofEpochMilli(end)), it)
            }
        }
        listener.onComplicationDataTimeline(ComplicationDataTimeline(first, entries))
    }

    override fun preview() = tide("05:12", "11:40")

    private fun times(extremes: List<Field.Extreme>, at: Long, zone: ZoneId): ComplicationData? {
        val high = Field.next(extremes, at, high = true) ?: return null
        val low = Field.next(extremes, at, high = false) ?: return null
        return tide(clock(high.time, zone), clock(low.time, zone))
    }

    private fun tide(high: String, low: String): ComplicationData =
        ShortTextComplicationData.Builder(plain(high), plain("満潮 $high 干潮 $low"))
            .setTitle(plain(low))
            .build()
}

/** PHOTO_IMAGE: today's tide from 0 to 24 h, drawn to fit the face's tide window. */
class TideGraphDataSource : FieldDataSource(ComplicationType.PHOTO_IMAGE) {

    override fun answer(s: Snapshot, now: Long, zone: ZoneId, listener: ComplicationRequestListener) {
        val today = Instant.ofEpochMilli(now).atZone(zone).toLocalDate()
        val first = TideImage.draw(s, today, zone)?.let(::photo)
        if (first == null) {
            listener.onComplicationData(NoDataComplicationData())
            return
        }
        val entries = ArrayList<TimelineEntry>()
        TideImage.draw(s, today.plusDays(1), zone)?.let {
            val start = Instant.ofEpochMilli(startOfDay(today.plusDays(1), zone))
            entries += TimelineEntry(TimeInterval(start, start.plusSeconds(24 * 3600)), photo(it))
        }
        listener.onComplicationDataTimeline(ComplicationDataTimeline(first, entries))
    }

    override fun preview(): ComplicationData {
        val zone = ZoneId.systemDefault()
        val today = LocalDate.now(zone)
        val from = startOfDay(today, zone)
        val times = LongArray(49) { from + it * 3600_000L }
        val heights = DoubleArray(49) {
            0.8 * Math.cos(2 * Math.PI * (it - 5.2) / 12.42) + 0.2 * Math.cos(2 * Math.PI * (it - 5.2) / 24.84)
        }
        val sample = Snapshot(
            Double.NaN, Double.NaN, 0, Double.NaN, Double.NaN, 0,
            longArrayOf(from + (6 * 60 + 13) * 60_000L), longArrayOf(from + (16 * 60 + 38) * 60_000L),
            times, heights, 0, Double.NaN, Double.NaN, 0, "",
        )
        return photo(TideImage.draw(sample, today, zone)!!)
    }

    private fun photo(bitmap: Bitmap): ComplicationData =
        PhotoImageComplicationData.Builder(Icon.createWithBitmap(bitmap), plain("タイドグラフ")).build()
}

/** Draws the tide curve at twice the face's pixels (the window is 120 x 38). */
object TideImage {
    private const val W = 240
    private const val H = 76
    private const val PAD = 6f
    private val ACCENT = Color.rgb(0xE3, 0xA4, 0x46)

    fun draw(s: Snapshot, date: LocalDate, zone: ZoneId): Bitmap? {
        val from = startOfDay(date, zone)
        val to = startOfDay(date.plusDays(1), zone)
        val points = s.tideTimes.indices
            .filter { s.tideTimes[it] in from..to && !s.tideHeights[it].isNaN() }
            .map { s.tideTimes[it] to s.tideHeights[it] }
        if (points.size < 12) return null
        val lo = points.minOf { it.second }
        val hi = points.maxOf { it.second }
        val span = (hi - lo).takeIf { it > 1e-6 } ?: 1.0
        val x = { t: Long -> ((t - from).toFloat() / (to - from)) * W }
        val y = { h: Double -> (PAD + (1 - (h - lo) / span) * (H - 2 * PAD - 4)).toFloat() }

        val bitmap = Bitmap.createBitmap(W, H, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val path = Path()
        points.forEachIndexed { i, (t, h) ->
            if (i == 0) path.moveTo(x(t), y(h)) else path.lineTo(x(t), y(h))
        }
        canvas.drawPath(path, Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 3.2f
            strokeJoin = Paint.Join.ROUND
            color = ACCENT
        })
        // Daylight as a thin bar along the bottom.
        val rise = s.sunrise.firstOrNull { it in from until to }
        val set = s.sunset.firstOrNull { it in from until to }
        if (rise != null && set != null && set > rise) {
            canvas.drawRect(x(rise), H - 3f, x(set), H.toFloat(), Paint().apply {
                color = ACCENT
                alpha = 180
            })
        }
        return bitmap
    }
}
