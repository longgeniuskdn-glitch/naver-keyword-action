package com.myvision.naverclipautoswipe

import android.app.Service
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.IBinder
import android.provider.Settings
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import kotlinx.coroutines.*

class PairingOverlayService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var windowManager: WindowManager? = null
    private var panel: LinearLayout? = null
    private var mdns: AdbMdns? = null
    private var pairingHost = ""
    private var pairingPort = 0
    private val codeBuffer = StringBuilder()
    private lateinit var statusText: TextView
    private lateinit var codeDisplay: TextView
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
            setPadding(dp(14), dp(12), dp(14), dp(12))
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
            textSize = 13f
            setPadding(0, dp(5), 0, dp(7))
        }
        box.addView(statusText)

        codeDisplay = TextView(this).apply {
            text = "— — — — — —"
            setTextColor(Color.WHITE)
            textSize = 22f
            gravity = Gravity.CENTER
            setTypeface(Typeface.MONOSPACE, Typeface.BOLD)
            setPadding(0, dp(3), 0, dp(7))
            background = rounded(Color.rgb(30, 41, 59), dp(12))
        }
        box.addView(codeDisplay, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(48)))

        addDigitRow(box, listOf("1", "2", "3", "4", "5"))
        addDigitRow(box, listOf("6", "7", "8", "9", "0"))

        val actionRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val erase = makeKey("⌫").apply { setOnClickListener { backspace() } }
        actionRow.addView(erase, LinearLayout.LayoutParams(0, dp(46), 1f).apply { rightMargin = dp(6) })

        val clear = makeKey("지우기").apply { setOnClickListener { clearCode() } }
        actionRow.addView(clear, LinearLayout.LayoutParams(0, dp(46), 1f).apply { rightMargin = dp(6) })

        connectButton = Button(this).apply {
            text = "연결"
            isAllCaps = false
            textSize = 15f
            isEnabled = false
            setTextColor(Color.rgb(11, 18, 32))
            background = rounded(Color.rgb(34, 211, 167), dp(12))
            setOnClickListener { submitCode() }
        }
        actionRow.addView(connectButton, LinearLayout.LayoutParams(0, dp(46), 1.35f))
        box.addView(actionRow, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(6) })

        val cancel = TextView(this).apply {
            text = "취소"
            setTextColor(Color.rgb(148, 163, 184))
            textSize = 12f
            gravity = Gravity.END
            setPadding(0, dp(6), 0, 0)
            setOnClickListener { stopSelf() }
        }
        box.addView(cancel)

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            y = dp(12)
            width = resources.displayMetrics.widthPixels - dp(18)
        }

        panel = box
        windowManager?.addView(box, params)
    }

    private fun addDigitRow(parent: LinearLayout, digits: List<String>) {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        digits.forEachIndexed { index, digit ->
            val button = makeKey(digit).apply { setOnClickListener { appendDigit(digit) } }
            row.addView(button, LinearLayout.LayoutParams(0, dp(44), 1f).apply {
                if (index < digits.lastIndex) rightMargin = dp(5)
            })
        }
        parent.addView(row, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(6) })
    }

    private fun makeKey(label: String) = Button(this).apply {
        text = label
        isAllCaps = false
        textSize = 15f
        setTextColor(Color.WHITE)
        background = rounded(Color.rgb(30, 41, 59), dp(10))
        setPadding(0, 0, 0, 0)
    }

    private fun appendDigit(digit: String) {
        if (codeBuffer.length >= 6) return
        codeBuffer.append(digit)
        updateCodeDisplay()
    }

    private fun backspace() {
        if (codeBuffer.isNotEmpty()) codeBuffer.deleteCharAt(codeBuffer.length - 1)
        updateCodeDisplay()
    }

    private fun clearCode() {
        codeBuffer.setLength(0)
        updateCodeDisplay()
    }

    private fun updateCodeDisplay() {
        val slots = (0 until 6).joinToString(" ") { i -> if (i < codeBuffer.length) codeBuffer[i].toString() else "—" }
        codeDisplay.text = slots
        connectButton.isEnabled = codeBuffer.length == 6 && pairingPort > 0
        connectButton.alpha = if (connectButton.isEnabled) 1f else .55f
    }

    private fun startDiscovery() {
        mdns = AdbMdns(this, AdbMdns.TLS_PAIRING) { host, port ->
            if (host.isNotBlank() && port > 0) {
                pairingHost = host
                pairingPort = port
                scope.launch {
                    statusText.text = "페어링 주소 $host:$port 감지 · 아래 숫자패드로 6자리를 입력하세요."
                    statusText.setTextColor(Color.rgb(110, 231, 183))
                    updateCodeDisplay()
                }
            } else {
                pairingPort = 0
                scope.launch {
                    statusText.text = "페어링 창이 닫혔습니다. ‘페어링 코드로 기기 페어링’을 다시 눌러주세요."
                    statusText.setTextColor(Color.rgb(253, 186, 116))
                    updateCodeDisplay()
                }
            }
        }.also { it.start() }
    }

    private fun submitCode() {
        val code = codeBuffer.toString()
        if (pairingPort <= 0) {
            statusText.text = "페어링 포트를 찾지 못했습니다. 페어링 코드 창을 다시 열어주세요."
            return
        }
        if (!Regex("\\d{6}").matches(code)) {
            statusText.text = "화면에 보이는 6자리 숫자를 입력해주세요."
            return
        }

        connectButton.isEnabled = false
        statusText.text = "페어링 경로를 자동으로 찾는 중…"
        statusText.setTextColor(Color.rgb(203, 213, 225))
        scope.launch {
            AdbEngine.pair(this@PairingOverlayService, pairingHost, code, pairingPort)
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
                    statusText.text = error.message ?: "연결 실패"
                    statusText.setTextColor(Color.rgb(253, 186, 116))
                    clearCode()
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
