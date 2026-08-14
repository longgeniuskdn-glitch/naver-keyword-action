package com.myvision.naverclipautoswipe

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.widget.Toast
import androidx.core.app.NotificationCompat
import androidx.core.app.RemoteInput
import kotlinx.coroutines.*

class PairingService : Service() {
    private enum class State { WAITING, READY, PAIRING, FAILED }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var mdns: AdbMdns? = null
    private var state = State.WAITING
    private var pairingPort = 0
    private var failureText: String? = null

    private val nm: NotificationManager get() = getSystemService(NotificationManager::class.java)

    override fun onCreate() {
        super.onCreate()
        createChannel()
        startForeground(NOTIFICATION_ID, buildNotification())
        startDiscovery()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, buildNotification())
        startDiscovery()
        if (intent?.action == ACTION_SUBMIT) {
            val code = intent.getStringExtra(EXTRA_CODE).orEmpty()
            val port = intent.getIntExtra(EXTRA_PORT, pairingPort)
            submitCode(code, port)
        }
        return START_NOT_STICKY
    }

    private fun startDiscovery() {
        if (mdns != null) return
        mdns = AdbMdns(this, AdbMdns.TLS_PAIRING) { port ->
            if (port > 0 && state != State.PAIRING) {
                pairingPort = port
                state = State.READY
                failureText = null
                nm.notify(NOTIFICATION_ID, buildNotification())
            }
        }.also { it.start() }
    }

    private fun submitCode(code: String, port: Int) {
        if (state == State.PAIRING) return
        state = State.PAIRING
        nm.notify(NOTIFICATION_ID, buildNotification())
        scope.launch {
            AdbEngine.pair(this@PairingService, code, port)
                .onSuccess {
                    Toast.makeText(this@PairingService, "연결 등록 완료", Toast.LENGTH_LONG).show()
                    val intent = Intent(this@PairingService, MainActivity::class.java).apply {
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                        putExtra(MainActivity.EXTRA_FROM_PAIRING, true)
                    }
                    try { startActivity(intent) } catch (_: Throwable) { }
                    stopSelf()
                }
                .onFailure { e ->
                    state = State.FAILED
                    failureText = e.message ?: "페어링 실패"
                    nm.notify(NOTIFICATION_ID, buildNotification())
                    Toast.makeText(this@PairingService, failureText, Toast.LENGTH_LONG).show()
                }
        }
    }

    private fun buildNotification(): Notification {
        val title = when (state) {
            State.WAITING -> "페어링 화면을 기다리는 중"
            State.READY -> "6자리 페어링 코드 입력"
            State.PAIRING -> "연결 중…"
            State.FAILED -> "연결 실패 · 다시 입력"
        }
        val text = when (state) {
            State.WAITING -> "무선 디버깅 → 페어링 코드로 기기 페어링을 누르세요."
            State.READY -> "알림의 코드 입력을 눌러 화면에 보이는 6자리를 입력하세요."
            State.PAIRING -> "휴대폰 내부 ADB와 연결하고 있습니다."
            State.FAILED -> failureText ?: "새 코드를 받아 다시 시도하세요."
        }
        val builder = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setOnlyAlertOnce(true)
            .setOngoing(state == State.PAIRING)
            .setContentIntent(openAppPendingIntent())
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "취소", cancelPendingIntent())

        if (state == State.READY || state == State.FAILED) {
            val remoteInput = RemoteInput.Builder(PairingReplyReceiver.KEY_CODE)
                .setLabel("6자리 코드")
                .build()
            val replyIntent = Intent(this, PairingReplyReceiver::class.java).apply {
                action = PairingReplyReceiver.ACTION_INPUT
                putExtra(PairingReplyReceiver.EXTRA_PORT, pairingPort)
            }
            val pending = PendingIntent.getBroadcast(
                this, 31, replyIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
            )
            builder.addAction(
                NotificationCompat.Action.Builder(android.R.drawable.ic_input_add, "코드 입력", pending)
                    .addRemoteInput(remoteInput)
                    .build()
            )
        }
        return builder.build()
    }

    private fun openAppPendingIntent(): PendingIntent = PendingIntent.getActivity(
        this, 32,
        Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
    )

    private fun cancelPendingIntent(): PendingIntent = PendingIntent.getBroadcast(
        this, 33,
        Intent(this, PairingReplyReceiver::class.java).setAction(PairingReplyReceiver.ACTION_CANCEL),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
    )

    private fun createChannel() {
        val channel = NotificationChannel(CHANNEL, "자동넘김 연결 설정", NotificationManager.IMPORTANCE_DEFAULT).apply {
            description = "무선 디버깅 페어링 코드를 입력합니다."
            setShowBadge(false)
        }
        nm.createNotificationChannel(channel)
    }

    override fun onDestroy() {
        mdns?.stop()
        mdns = null
        scope.cancel()
        nm.cancel(NOTIFICATION_ID)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        const val ACTION_SUBMIT = "com.myvision.naverclipautoswipe.SUBMIT_PAIR_CODE"
        const val EXTRA_CODE = "pair_code"
        const val EXTRA_PORT = "pair_port"
        private const val CHANNEL = "local_adb_pairing"
        private const val NOTIFICATION_ID = 4201
    }
}
