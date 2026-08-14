package com.myvision.naverclipautoswipe

import android.app.Service
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.IBinder
import android.provider.Settings
import android.text.InputFilter
import android.view.Gravity
import android.view.WindowManager
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import kotlinx.coroutines.*

class PairingOverlayService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var windowManager: WindowManager? = null
    private var panel: LinearLayout? = null
    private var mdns: AdbMdns? = null
    private var pairingPort = 0
    private lateinit var statusText: TextView
    private lateinit var codeInput: EditText
    private lateinit var connectButton: Button

    override fun onCreate() {
        super.onCreate()
        if (!Settings.canDrawOverlays(this)) {
            stopSelf()
            return
        }
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        showPanel()
        startDiscovery()
    }

    private fun showPanel() {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(14), dp(18), dp(14))
            background = rounded(Color.rgb(15, 23, 42), dp(18))
            elevation = dp(12).toFloat()
        }

        val title = TextView(this).apply {
            text = "클립 자동넘김 · 최초 연결"
            setTextColor(Color.WHITE)
            textSize = 16f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        }
        box.addView(title)

        statusText = TextView(this).apply {
            text = "무선 디버깅에서 ‘페어링 코드로 기기 페어링’을 눌러주세요."
            setTextColor(Color.rgb(203, 213, 225))
            textSize = 14f
            setPadding(0, dp(7), 0, dp(10))
        }
        box.addView(statusText)

        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        codeInput = EditText(this).apply {
            hint = "6자리 코드"
            setHintTextColor(Color.rgb(100, 116, 139))
            setTextColor(Color.WHITE)
            textSize = 19f
            gravity = Gravity.CENTER
            inputType = android.text.InputType.TYPE_CLASS_NUMBER
            filters = arrayOf(InputFilter.LengthFilter(6))
            isSingleLine = true
            isEnabled = false
            background = rounded(Color.rgb(30, 41, 59), dp(12))
            setPadding(dp(10), 0, dp(10), 0)
        }
        row.addView(codeInput, LinearLayout.LayoutParams(0, dp(52), 1f).apply { rightMargin = dp(8) })

        connectButton = Button(this).apply {
            text = "연결"
            isAllCaps = false
            textSize = 15f
            isEnabled = false
            setTextColor(Color.rgb(11, 18, 32))
            background = rounded(Color.rgb(34, 211, 167), dp(12))
            setOnClickListener { submitCode() }
        }
        row.addView(connectButton, LinearLayout.LayoutParams(dp(84), dp(52)))
        box.addView(row)

        val cancel = TextView(this).apply {
            text = "취소"
            setTextColor(Color.rgb(148, 163, 184))
            textSize = 13f
            gravity = Gravity.END
            setPadding(0, dp(8), 0, 0)
            setOnClickListener { stopSelf() }
        }
        box.addView(cancel)

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            y = dp(24)
            width = resources.displayMetrics.widthPixels - dp(24)
        }

        panel = box
        windowManager?.addView(box, params)
    }

    private fun startDiscovery() {
        mdns = AdbMdns(this, AdbMdns.TLS_PAIRING) { port ->
            if (port > 0) {
                pairingPort = port
                scope.launch {
                    statusText.text = "6자리 코드가 감지됐습니다. 아래에 그대로 입력하세요."
                    statusText.setTextColor(Color.rgb(110, 231, 183))
                    codeInput.isEnabled = true
                    connectButton.isEnabled = true
                    codeInput.requestFocus()
                    try {
                        val imm = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
                        imm.showSoftInput(codeInput, InputMethodManager.SHOW_IMPLICIT)
                    } catch (_: Throwable) { }
                }
            }
        }.also { it.start() }
    }

    private fun submitCode() {
        val code = codeInput.text?.toString()?.trim().orEmpty()
        if (pairingPort <= 0) {
            statusText.text = "아직 페어링 화면을 찾지 못했습니다. 페어링 코드 창을 열어주세요."
            return
        }
        if (!Regex("\\d{6}").matches(code)) {
            statusText.text = "화면에 보이는 6자리 숫자를 입력해주세요."
            return
        }

        codeInput.isEnabled = false
        connectButton.isEnabled = false
        statusText.text = "연결 중…"
        scope.launch {
            AdbEngine.pair(this@PairingOverlayService, code, pairingPort)
                .onSuccess {
                    statusText.text = "연결 등록 완료 · 잠시 후 앱으로 돌아갑니다."
                    statusText.setTextColor(Color.rgb(110, 231, 183))
                    delay(800)
                    try {
                        startActivity(Intent(this@PairingOverlayService, MainActivity::class.java).apply {
                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                        })
                    } catch (_: Throwable) { }
                    stopSelf()
                }
                .onFailure { error ->
                    statusText.text = error.message ?: "연결 실패 · 새 코드를 받아 다시 시도해주세요."
                    statusText.setTextColor(Color.rgb(253, 186, 116))
                    codeInput.text?.clear()
                    codeInput.isEnabled = true
                    connectButton.isEnabled = true
                }
        }
    }

    override fun onDestroy() {
        mdns?.stop()
        mdns = null
        scope.cancel()
        panel?.let {
            try { windowManager?.removeView(it) } catch (_: Throwable) { }
        }
        panel = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun rounded(color: Int, radius: Int) = GradientDrawable().apply {
        setColor(color)
        cornerRadius = radius.toFloat()
    }

    private fun dp(v: Int) = Math.round(v * resources.displayMetrics.density)
}
