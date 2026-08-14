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
            failureMessage = "페어링 주소를 찾지 못했습니다. 새 페어링 코드를 열어주세요."
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
            State.WAITING -> "클립 자동넘김 · 페어링 준비됨" to "무선 디버깅에서 ‘페어링 코드로 기기 페어링’을 여세요. 코드가 감지되면 이 알림에 입력 버튼이 나타납니다."
            State.READY -> "👇 6자리 코드 입력" to "삼성의 기기 페어링 창은 그대로 두고, 이 알림의 ‘6자리 코드 입력’ 버튼을 누르세요."
            State.PAIRING -> "클립 자동넘김 · 연결 중" to "$pairingHost:$pairingPort 로 연결하고 있습니다."
            State.FAILED -> "👇 다시 6자리 코드 입력" to failureMessage
        }

        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setColor(Color.rgb(34, 211, 167))
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setDefaults(Notification.DEFAULT_ALL)
            .setOnlyAlertOnce(false)
            .setOngoing(state == State.WAITING || state == State.READY || state == State.PAIRING)
            .setContentIntent(openAppPendingIntent())

        if (state == State.READY || state == State.FAILED) {
            val remoteInput = RemoteInput.Builder(KEY_CODE)
                .setLabel("6자리 코드 입력")
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
            val replyAction = NotificationCompat.Action.Builder(
                android.R.drawable.ic_input_add,
                "6자리 코드 입력",
                replyPendingIntent
            )
                .addRemoteInput(remoteInput)
                .setAllowGeneratedReplies(true)
                .setSemanticAction(NotificationCompat.Action.SEMANTIC_ACTION_REPLY)
                .setShowsUserInterface(true)
                .build()

            // 삼성 One UI에서 액션이 접혀 숨지 않도록 입력 액션 하나만 둔다.
            builder.addAction(replyAction)
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

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < 26) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "6자리 페어링 코드 입력",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "무선 디버깅 최초 페어링 코드를 알림에서 직접 입력합니다."
            enableVibration(true)
            setShowBadge(false)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
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
        const val EXTRA_CODE = "pairing_code"
        const val EXTRA_HOST = "pairing_host"
        const val EXTRA_PORT = "pairing_port"
        const val KEY_CODE = "pairing_code_reply"
        private const val CHANNEL_ID = "pairing_notification_v035"
        private const val NOTIFICATION_ID = 4501
        private const val REQUEST_REPLY = 4502
        private const val REQUEST_OPEN_APP = 4503
    }
}
