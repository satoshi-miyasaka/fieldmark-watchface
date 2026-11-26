package io.github.satoshimiyasaka.fieldmark

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.work.WorkManager
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * The companion's only screen: asks for location, shows what the last update
 * found and can update now. Opening it once is enough; after that the watch
 * updates every hour on its own.
 */
class MainActivity : ComponentActivity() {

    private lateinit var status: TextView
    private lateinit var permissionButton: Button
    private lateinit var backgroundButton: Button

    private val askLocation = registerForActivityResult(ActivityResultContracts.RequestPermission()) {
        refresh()
        if (it) Updater.now(this)
    }

    private val askBackground = registerForActivityResult(ActivityResultContracts.RequestPermission()) {
        refresh()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val pad = (resources.displayMetrics.widthPixels * 0.14f).toInt()
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(pad, pad / 2, pad, pad)
        }
        column.addView(TextView(this).apply {
            text = "FIELDMARK"
            textSize = 16f
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(0xE0, 0x78, 0x2F))
        })
        status = TextView(this).apply {
            textSize = 12f
            setPadding(0, pad / 4, 0, pad / 4)
        }
        column.addView(status)
        permissionButton = button("位置の利用を許可") { askLocation.launch(Manifest.permission.ACCESS_COARSE_LOCATION) }
        backgroundButton = button("常に位置を使う") { askBackground.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION) }
        column.addView(permissionButton)
        column.addView(backgroundButton)
        column.addView(button("今すぐ更新") {
            status.text = "更新しています…"
            Updater.now(this)
        })
        setContentView(ScrollView(this).apply { addView(column) })

        Updater.schedule(this)
        WorkManager.getInstance(this).getWorkInfosForUniqueWorkLiveData(Updater.WORK_NOW).observe(this) { infos ->
            if (infos.any { it.state.isFinished }) refresh()
        }
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    private fun button(label: String, onClick: () -> Unit) = Button(this).apply {
        text = label
        isAllCaps = false
        setOnClickListener { onClick() }
    }

    private fun granted(permission: String) =
        ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED

    private fun refresh() {
        val location = granted(Manifest.permission.ACCESS_COARSE_LOCATION)
        val background = granted(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        permissionButton.visibility = if (location) android.view.View.GONE else android.view.View.VISIBLE
        backgroundButton.visibility = if (location && !background) android.view.View.VISIBLE else android.view.View.GONE

        val s = Store.load(this)
        val zone = ZoneId.systemDefault()
        val time = { t: Long -> DateTimeFormatter.ofPattern("M/d HH:mm").format(Instant.ofEpochMilli(t).atZone(zone)) }
        val lines = ArrayList<String>()
        lines += if (s.updatedAt > 0) "${time(s.updatedAt)} ${s.status}" else "まだ更新していません"
        if (s.hasLocation) lines += String.format(Locale.US, "位置 %.2f, %.2f", s.lat, s.lon)
        if (s.windAt > 0) {
            lines += String.format(Locale.US, "風 %s %.1f m/s", Field.compassPoint(s.windDirection), s.windSpeed)
        }
        lines += if (s.hasTide) "潮位 あり" else "潮位 なし(海から遠い場所では出ません)"
        if (!background && location) lines += "「常に位置を使う」を許可すると、移動しても自動で場所が変わります"
        status.text = lines.joinToString("\n")
    }
}
