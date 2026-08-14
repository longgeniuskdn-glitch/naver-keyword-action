package com.myvision.naverclipautoswipe

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.graphics.Color
import android.os.Build
import android.os.IBinder
import android.widget.Toast
import androidx.core.app.NotificationCompat
import androidx.core.app.RemoteInput
import kotlinx.coroutines.*

class PairingNotificationService : Service() {
    private enum class State { WAITING, READY, PAIRING, FAILED }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var mdns: AdbMdns? = null
    private var state = State.WAITING
    private var pairingHost = ""
    private var pairingPort = 0
    private var failureMessage = ""

    private val notificationManager: NotificationManager
        get() = getSystemService(NotificationManager::class.java)

    override fun onCreate() {
        super.onCreate()
        createChannel()
        startForeground(NOTIFICATION_ID, buildNotification())
        startDiscovery()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, buildNotification())
        startDiscovery()
        if (intent?.action == ACTION_SUBMIT_CODE) {
            val code = intent.getStringExtra(EXTRA_CODE).orEmpty()
            val host = intent.getStringExtra(EXTRA_HOST).orEmpty().ifBlank { pairingHost }
            val port = intent.getIntExtra(EXTRA_PORT, pairingPort)
            submitCode(code, host, port)
        }
        if (intent?.action == ACTION_CANCEL) stopSelf()
        return START_NOT_STICKY
    }

    private fun startDiscovery() {
        if (mdns != null) return
        mdns = AdbMdns(this, AdbMdns.TLS_PAIRING) { host, port ->
            if (host.isNotBlank() && port > 0 && state != State.PAIRING) {
                pairingHost = host
                pairingPort = port
                state = State.READY
                failureMessage = ""
                notificationManager.notify(NOTIFICATION_ID, buildNotification())
            }
        }.also { it.start() }
    }

    private fun submitCode(codeRaw: String, host: String, port: Int) {
        val code = codeRaw.trim()
        if (!Regex("\\d{6}").matches(code)) {
            state = State.FAILED
            failureMessage = "6자리 숫자를 입력해주세요."
            notificationManager.notify(NOTIFICATION_ID, buildNotification())
            return
        }
        if (host.isBlank() || port !in 1..65535) {
            state = State.FAILED
            failureMessage = "페어링 주소를 찾지 못했습니다. 새 코드를 열어주세요."
            notificationManager.notify(NOTIFICATION_ID, buildNotification())
            return
        }

        state = State.PAIRING
        notificationManager.notify(NOTIFICATION_ID, buildNotification())
        scope.launch {
            AdbEngine.pair(this@PairingNotificationService, host, code, port)
                .onSuccess {
                    Toast.makeText(this@PairingNotificationService, "연결 등록 완료", Toast.LENGTH_LONG).show()
                    notificationManager.notify(NOTIFICATION_ID, successNotification())
                    delay(650)
                    try {
                        startActivity(Intent(this@PairingNotificationService, MainActivity::class.java).apply {
                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                        })
                    } catch (_: Throwable) { }
                    stopSelf()
                }
                .onFailure { error ->
                    state = State.FAILED
                    failureMessage = error.message ?: "페어링 실패"
                    notificationManager.notify(NOTIFICATION_ID, buildNotification())
                }
        }
    }

    private fun buildNotification(): Notification {
        val (title, text) = when (state) {
            State.WAITING -> "클립 자동넘김 · 페어링 준비됨" to "무선 디버깅에서 ‘페어링 코드로 기기 페어링’을 여세요."
            State.READY -> "클립 자동넘김 · 6자리 코드 입력" to "설정의 코드 창은 그대로 두고 ‘코드 입력’을 눌러 6자리를 보내세요."
            State.PAIRING -> "클립 자동넘김 · 연결 중" to "$pairingHost:$pairingPort 로 연결하고 있습니다."
            State.FAILED -> "클립 자동넘김 · 다시 시도" to failureMessage
        }

        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setColor(Color.rgb(34, 211, 167))
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setOnlyAlertOnce(false)
            .setOngoing(state == State.PAIRING)
            .setContentIntent(openAppPendingIntent())
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "취소", cancelPendingIntent())

        if (state == State.READY || state == State.FAILED) {
            val remoteInput = RemoteInput.Builder(KEY_CODE)
                .setLabel("6자리 코드")
                .build()
            val replyIntent = Intent(this, PairingReplyReceiver::class.java).apply {
                action = PairingReplyReceiver.ACTION_INPUT
                putExtra(EXTRA_HOST, pairingHost)
                putExtra(EXTRA_PORT, pairingPort)
            }
            val replyPendingIntent = PendingIntent.getBroadcast(
                this,
                REQUEST_REPLY,
                replyIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
            )
            builder.addAction(
                NotificationCompat.Action.Builder(
                    android.R.drawable.ic_input_add,
                    "코드 입력",
                    replyPendingIntent
                ).addRemoteInput(remoteInput).build()
            )
        }
        return builder.build()
    }

    private fun successNotification(): Notification = NotificationCompat.Builder(this, CHANNEL_ID)
        .setSmallIcon(android.R.drawable.checkbox_on_background)
        .setColor(Color.rgb(34, 211, 167))
        .setContentTitle("클립 자동넘김 · 연결 완료")
        .setContentText("앱으로 돌아가 플로팅 버튼을 준비합니다.")
        .setAutoCancel(true)
        .setContentIntent(openAppPendingIntent())
        .build()

    private fun openAppPendingIntent(): PendingIntent = PendingIntent.getActivity(
        this,
        REQUEST_OPEN_APP,
        Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
    )

    private fun cancelPendingIntent(): PendingIntent = PendingIntent.getService(
        this,
        REQUEST_CANCEL,
        Intent(this, PairingNotificationService::class.java).setAction(ACTION_CANCEL),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
    )

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < 26) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "최초 연결 설정",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "무선 디버깅 최초 페어링 코드를 입력합니다."
            enableVibration(true)
            setShowBadge(false)
        }
        notificationManager.createNotificationChannel(channel)
    }

    override fun onDestroy() {
        mdns?.stop()
        mdns = null
        scope.cancel()
        try { notificationManager.cancel(NOTIFICATION_ID) } catch (_: Throwable) { }
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        const val ACTION_SUBMIT_CODE = "com.myvision.naverclipautoswipe.SUBMIT_PAIR_CODE"
        const val ACTION_CANCEL = "com.myvision.naverclipautoswipe.CANCEL_PAIR"
        const val EXTRA_CODE = "pairing_code"
        const val EXTRA_HOST = "pairing_host"
        const val EXTRA_PORT = "pairing_port"
        const val KEY_CODE = "pairing_code_reply"
        private const val CHANNEL_ID = "pairing_notification_v034"
        private const val NOTIFICATION_ID = 4401
        private const val REQUEST_REPLY = 4402
        private const val REQUEST_OPEN_APP = 4403
        private const val REQUEST_CANCEL = 4404
    }
}
