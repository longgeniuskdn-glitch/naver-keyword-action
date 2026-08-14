package com.myvision.naverclipautoswipe

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.graphics.*
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.Settings
import android.view.*
import android.widget.Toast
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.*
import java.util.Random

class OverlayService : Service() {
    private val handler = Handler(Looper.getMainLooper())
    private val random = Random()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private lateinit var windowManager: WindowManager
    private var button: FloatingButtonView? = null
    private lateinit var params: WindowManager.LayoutParams
    private var running = false
    private val prefs by lazy { getSharedPreferences("overlay", MODE_PRIVATE) }

    override fun onCreate() {
        super.onCreate()
        if (!Settings.canDrawOverlays(this)) { stopSelf(); return }
        createChannel()
        startForeground(NOTIFICATION_ID, NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentTitle("클립 자동넘김 준비")
            .setContentText("짧게: 시작/중지 · 길게: 버튼 숨기기")
            .setOnlyAlertOnce(true)
            .setOngoing(true)
            .setContentIntent(PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
            .build())
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        createFloatingButton()
    }

    private fun createChannel() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, "자동넘김 실행", NotificationManager.IMPORTANCE_LOW).apply { setShowBadge(false) })
    }

    private fun createFloatingButton() {
        if (button != null) return
        val size = dp(62)
        params = WindowManager.LayoutParams(
            size,
            size,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        )
        params.gravity = Gravity.TOP or Gravity.START
        val display = getScreenSize()
        params.x = prefs.getInt("x", maxOf(dp(12), display.x - size - dp(18)))
        params.y = prefs.getInt("y", display.y / 3)
        button = FloatingButtonView()
        windowManager.addView(button, params)
    }

    private fun getScreenSize(): Point {
        val p = Point()
        @Suppress("DEPRECATION") windowManager.defaultDisplay.getRealSize(p)
        return p
    }

    private fun toggle() = setRunning(!running)

    private fun setRunning(value: Boolean) {
        running = value
        handler.removeCallbacksAndMessages(null)
        button?.invalidate()
        if (running) scheduleNext()
    }

    private fun scheduleNext() {
        handler.removeCallbacksAndMessages(null)
        if (!running) return
        val delayMs = 15_000L + random.nextInt(15_001)
        handler.postDelayed({ performSwipe() }, delayMs)
    }

    private fun scheduleRetry() {
        handler.removeCallbacksAndMessages(null)
        if (!running) return
        handler.postDelayed({ performSwipe() }, RETRY_DELAY_MS)
    }

    private fun performSwipe() {
        if (!running) return
        val s = getScreenSize()
        val x = s.x / 2
        val y1 = (s.y * 0.78f).toInt()
        val y2 = (s.y * 0.27f).toInt()
        scope.launch {
            val result = AdbEngine.runShell(this@OverlayService, "input swipe $x $y1 $x $y2 360")
            withContext(Dispatchers.Main) {
                if (!running) return@withContext
                if (result.isFailure) {
                    // ADB가 순간적으로 끊겨도 사용자가 멈출 때까지 자동으로 재연결/재시도한다.
                    scheduleRetry()
                } else {
                    scheduleNext()
                }
            }
        }
    }

    private fun hideFloatingButton() {
        setRunning(false)
        button?.let { view ->
            try { windowManager.removeView(view) } catch (_: Throwable) { }
        }
        button = null
        Toast.makeText(this, "버튼을 숨겼습니다. 다시 보려면 앱을 열어주세요.", Toast.LENGTH_SHORT).show()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        scope.cancel()
        button?.let { try { windowManager.removeView(it) } catch (_: Throwable) { } }
        button = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
    private fun dp(v: Int) = Math.round(v * resources.displayMetrics.density)

    private inner class FloatingButtonView : View(this@OverlayService) {
        private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        private var downRawX = 0f
        private var downRawY = 0f
        private var downX = 0
        private var downY = 0
        private var moved = false
        private var longPressed = false
        private val hideRunnable = Runnable {
            if (!moved) {
                longPressed = true
                performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                hideFloatingButton()
            }
        }

        init { setLayerType(LAYER_TYPE_SOFTWARE, null) }

        override fun onDraw(c: Canvas) {
            super.onDraw(c)
            val cx = width / 2f
            val cy = height / 2f
            val radius = minOf(width, height) * 0.43f
            paint.setShadowLayer(dp(6).toFloat(), 0f, dp(2).toFloat(), 0x66000000)
            paint.color = if (running) Color.rgb(34, 211, 167) else Color.rgb(15, 23, 42)
            paint.style = Paint.Style.FILL
            c.drawCircle(cx, cy, radius, paint)
            paint.clearShadowLayer()
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = dp(2).toFloat()
            paint.color = Color.rgb(34, 211, 167)
            c.drawCircle(cx, cy, radius - dp(1), paint)
            paint.style = Paint.Style.FILL
            paint.color = Color.WHITE
            if (running) {
                val bw = dp(5).toFloat()
                val bh = dp(20).toFloat()
                val gap = dp(5).toFloat()
                c.drawRoundRect(RectF(cx-gap-bw, cy-bh/2, cx-gap, cy+bh/2), dp(2).toFloat(), dp(2).toFloat(), paint)
                c.drawRoundRect(RectF(cx+gap, cy-bh/2, cx+gap+bw, cy+bh/2), dp(2).toFloat(), dp(2).toFloat(), paint)
            } else {
                val p = Path()
                p.moveTo(cx-dp(7), cy-dp(12))
                p.lineTo(cx+dp(14), cy)
                p.lineTo(cx-dp(7), cy+dp(12))
                p.close()
                c.drawPath(p, paint)
            }
            paint.color = if (running) Color.WHITE else Color.rgb(34, 211, 167)
            c.drawCircle(cx+radius*.68f, cy-radius*.68f, dp(4).toFloat(), paint)
        }

        override fun onTouchEvent(e: MotionEvent): Boolean {
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downRawX = e.rawX
                    downRawY = e.rawY
                    downX = params.x
                    downY = params.y
                    moved = false
                    longPressed = false
                    postDelayed(hideRunnable, LONG_PRESS_MS)
                    animate().scaleX(.94f).scaleY(.94f).setDuration(70).start()
                    return true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = Math.round(e.rawX - downRawX)
                    val dy = Math.round(e.rawY - downRawY)
                    if (kotlin.math.abs(dx) > dp(5) || kotlin.math.abs(dy) > dp(5)) {
                        moved = true
                        removeCallbacks(hideRunnable)
                    }
                    params.x = downX + dx
                    params.y = downY + dy
                    try { windowManager.updateViewLayout(this, params) } catch (_: Throwable) { }
                    return true
                }
                MotionEvent.ACTION_UP -> {
                    removeCallbacks(hideRunnable)
                    if (longPressed) return true
                    animate().scaleX(1f).scaleY(1f).setDuration(90).start()
                    prefs.edit().putInt("x", params.x).putInt("y", params.y).apply()
                    if (!moved) toggle()
                    return true
                }
                MotionEvent.ACTION_CANCEL -> {
                    removeCallbacks(hideRunnable)
                    if (!longPressed) animate().scaleX(1f).scaleY(1f).setDuration(90).start()
                    return true
                }
            }
            return super.onTouchEvent(e)
        }
    }

    companion object {
        private const val CHANNEL = "autoswipe_runtime"
        private const val NOTIFICATION_ID = 4301
        private const val RETRY_DELAY_MS = 2_000L
        private const val LONG_PRESS_MS = 750L
    }
}
