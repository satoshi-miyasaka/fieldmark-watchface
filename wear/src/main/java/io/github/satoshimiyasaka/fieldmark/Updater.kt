package io.github.satoshimiyasaka.fieldmark

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.Tasks
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.TimeUnit

/**
 * Once an hour: find where the watch is (coarse, from the last fix when it is
 * recent), read wind and sunrise/sunset from Open-Meteo, and the tide when
 * it is six hours old or the watch has moved. One request each, so the
 * watch's radio is on for a few seconds an hour.
 */
object Updater {
    const val WORK_NOW = "update-now"
    private const val WORK_PERIODIC = "update-hourly"

    private val network = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

    fun schedule(context: Context) {
        val request = PeriodicWorkRequestBuilder<UpdateWorker>(1, TimeUnit.HOURS)
            .setConstraints(network)
            .build()
        WorkManager.getInstance(context)
            .enqueueUniquePeriodicWork(WORK_PERIODIC, ExistingPeriodicWorkPolicy.KEEP, request)
    }

    fun now(context: Context) {
        val request = OneTimeWorkRequestBuilder<UpdateWorker>().setConstraints(network).build()
        WorkManager.getInstance(context).enqueueUniqueWork(WORK_NOW, ExistingWorkPolicy.REPLACE, request)
    }
}

class UpdateWorker(context: Context, params: WorkerParameters) : Worker(context, params) {

    override fun doWork(): Result {
        val context = applicationContext
        val now = System.currentTimeMillis()
        locate(context, now)
        val s = Store.load(context)
        if (!s.hasLocation) {
            Store.saveStatus(context, "位置がわかりません。アプリで位置の利用を許可してください", now)
            return Result.success()
        }
        return try {
            Store.saveForecast(context, Field.parseForecast(get(Field.forecastUrl(s.lat, s.lon))))
            val moved = s.marineAt == 0L || s.marineLat.isNaN() ||
                Field.distanceKm(s.lat, s.lon, s.marineLat, s.marineLon) > 5
            if (moved || now - s.marineAt > MARINE_EVERY) {
                Store.saveMarine(context, Field.parseMarine(get(Field.marineUrl(s.lat, s.lon))), s.lat, s.lon, now)
            }
            Store.saveStatus(context, "更新しました", now)
            Store.refreshWatchFace(context)
            Result.success()
        } catch (e: Exception) {
            Store.saveStatus(context, "取得できませんでした (${e.javaClass.simpleName})", now)
            Result.retry()
        }
    }

    /** Coarse location: the last fix if it is under an hour old, else a fresh balanced-power fix. */
    private fun locate(context: Context, now: Long) {
        val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
        if (!granted) return
        try {
            val client = LocationServices.getFusedLocationProviderClient(context)
            var location: Location? = Tasks.await(client.lastLocation, 10, TimeUnit.SECONDS)
            if (location == null || now - location.time > LOCATION_MAX_AGE) {
                location = Tasks.await(
                    client.getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, null),
                    30, TimeUnit.SECONDS,
                ) ?: location
            }
            if (location != null) Store.saveLocation(context, location.latitude, location.longitude, location.time)
        } catch (e: Exception) {
            // Keep the last known place; camp sites do not move.
        }
    }

    private fun get(url: String): String {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.connectTimeout = 15_000
        connection.readTimeout = 15_000
        try {
            if (connection.responseCode != 200) throw java.io.IOException("HTTP ${connection.responseCode}")
            return connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private companion object {
        const val LOCATION_MAX_AGE = 60 * 60 * 1000L
        const val MARINE_EVERY = 6 * 60 * 60 * 1000L
    }
}
