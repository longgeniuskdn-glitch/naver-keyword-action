package com.myvision.naverclipautoswipe

import android.Manifest
import android.app.Activity
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import kotlinx.coroutines.*

class MainActivity : Activity() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private lateinit var status: TextView
    private lateinit var guide: TextView
    private lateinit var action: Button
    private var adbReady = false
    private var checking = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.rgb(11, 18, 32)
        window.navigationBarColor = Color.rgb(11, 18, 32)
        buildUi()
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(26), dp(42), dp(26), dp(30))
            setBackgroundColor(Color.rgb(11, 18, 32))
        }

        val mark = TextView(this).apply {
            text = "▶"; setTextColor(Color.WHITE); textSize = 34f; gravity = Gravity.CENTER
            background = circle(Color.rgb(34, 211, 167))
        }
        root.addView(mark, LinearLayout.LayoutParams(dp(80), dp(80)))

        val title = TextView(this).apply {
            text = "클립 자동넘김"; setTextColor(Color.WHITE); textSize = 27f; gravity = Gravity.CENTER
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        }
        root.addView(title, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(20) })

        val subtitle = TextView(this).apply {
            text = "추가 앱 없이 작동하는 v0.3.8"; setTextColor(Color.rgb(148, 163, 184)); textSize = 15f; gravity = Gravity.CENTER
        }
        root.addView(subtitle, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(8) })

        status = TextView(this).apply {
            gravity = Gravity.CENTER; textSize = 15f; setTypeface(Typeface.DEFAULT, Typeface.BOLD); setPadding(dp(16), dp(10), dp(16), dp(10))
        }
        root.addView(status, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(26) })

        guide = TextView(this).apply {
            setTextColor(Color.rgb(226, 232, 240)); textSize = 18f; gravity = Gravity.CENTER; setLineSpacing(0f, 1.24f)
        }
        root.addView(guide, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f).apply { topMargin = dp(28) })

        action = Button(this).apply {
            isAllCaps = false; textSize = 18f; setTypeface(Typeface.DEFAULT, Typeface.BOLD); setTextColor(Color.rgb(11, 18, 32))
            background = rounded(Color.rgb(34, 211, 167), dp(18)); setOnClickListener { doNext() }
        }
        root.addView(action, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(60)))

        val footer = TextView(this).apply {
            text = "15~30초 랜덤 · 최소 15초 / 최대 30초"; setTextColor(Color.rgb(100, 116, 139)); textSize = 13f; gravity = Gravity.CENTER
        }
        root.addView(footer, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(14) })
        setContentView(root)
    }

    private fun refresh() {
        if (checking) return
        checking = true
        setState("● 연결 확인 중", "휴대폰 내부 무선 ADB 연결을 확인하고 있습니다.", "잠시만 기다려주세요", false)
        scope.launch {
            adbReady = AdbEngine.isReady(this@MainActivity)
            checking = false
            updateUi()
        }
    }

    private fun updateUi() {
        when {
            !notificationGranted() -> setState(
                "● 연결 알림 권한 필요",
                "최초 페어링 동안 설정 화면을 그대로 유지하기 위해 알림의 답장칸에서 6자리 코드를 입력합니다.\n\n이 권한은 최초 연결 과정에만 필요합니다.",
                "① 연결 알림 허용",
                true
            )
            !adbReady -> setState(
                "● 최초 연결 필요",
                "아래 버튼을 누르면 먼저 ‘페어링 준비됨’ 알림을 띄운 뒤 무선 디버깅으로 이동합니다.\n\n1. ‘페어링 코드로 기기 페어링’ 누르기\n2. 코드 창은 그대로 둔 채 상단 알림창 내리기\n3. ‘코드 입력’에 6자리 입력 후 전송\n\n설정의 페어링 창을 누르거나 닫지 마세요.",
                "② 연결 시작",
                true
            )
            !Settings.canDrawOverlays(this) -> setState(
                "● 플로팅 버튼 권한 필요",
                "네이버 클립 위에 시작/중지 버튼 하나를 띄우기 위한 권한입니다.",
                "③ 플로팅 버튼 허용",
                true
            )
            else -> {
                setState(
                    "● 준비 완료",
                    "네이버 클립으로 이동하세요.\n\n짧게 터치: 시작 / 일시정지\n길게 누르기: 플로팅 버튼 숨기기\n\n정상 동작과 오류 재시도 모두 15~30초 랜덤입니다. 어떤 경우에도 15초보다 빠르거나 30초를 넘지 않습니다.",
                    "네이버 열기",
                    true
                )
                ensureOverlay()
            }
        }
    }

    private fun doNext() {
        when {
            !notificationGranted() -> {
                if (Build.VERSION.SDK_INT >= 33) {
                    requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_NOTIFICATIONS)
                }
            }
            !adbReady -> {
                val service = Intent(this, PairingNotificationService::class.java)
                if (Build.VERSION.SDK_INT >= 26) startForegroundService(service) else startService(service)
                scope.launch {
                    delay(650)
                    openWirelessDebuggingSettings()
                }
            }
            !Settings.canDrawOverlays(this) -> {
                startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
            }
            else -> {
                ensureOverlay()
                val naver = packageManager.getLaunchIntentForPackage("com.nhn.android.search")
                if (naver != null) startActivity(naver)
                else startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=com.nhn.android.search")))
            }
        }
    }

    private fun notificationGranted(): Boolean =
        Build.VERSION.SDK_INT < 33 || checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_NOTIFICATIONS) updateUi()
    }

    private fun openWirelessDebuggingSettings() {
        val intents = listOf(
            Intent("android.settings.WIRELESS_DEBUGGING_SETTINGS"),
            Intent().setComponent(ComponentName("com.android.settings", "com.android.settings.Settings\$WirelessDebuggingActivity")),
            Intent(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS),
            Intent(Settings.ACTION_SETTINGS)
        )
        for (intent in intents) {
            try {
                if (intent.resolveActivity(packageManager) != null) {
                    startActivity(intent)
                    return
                }
            } catch (_: Throwable) { }
        }
    }

    private fun ensureOverlay() {
        if (Settings.canDrawOverlays(this)) startService(Intent(this, OverlayService::class.java))
    }

    private fun setState(badge: String, body: String, button: String, enabled: Boolean) {
        status.text = badge
        status.setTextColor(Color.rgb(110, 231, 183))
        status.background = rounded(Color.rgb(6, 78, 59), dp(99))
        guide.text = body
        action.text = button
        action.isEnabled = enabled
        action.alpha = if (enabled) 1f else .55f
    }

    private fun rounded(color: Int, radius: Int) = GradientDrawable().apply { setColor(color); cornerRadius = radius.toFloat() }
    private fun circle(color: Int) = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(color) }
    private fun dp(v: Int) = Math.round(v * resources.displayMetrics.density)

    companion object {
        private const val REQUEST_NOTIFICATIONS = 84
    }
}
