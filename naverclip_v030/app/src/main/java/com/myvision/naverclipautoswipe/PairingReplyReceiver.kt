package com.myvision.naverclipautoswipe

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.RemoteInput

class PairingReplyReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_INPUT) return

        val code = RemoteInput.getResultsFromIntent(intent)
            ?.getCharSequence(PairingNotificationService.KEY_CODE)
            ?.toString()
            .orEmpty()

        val serviceIntent = Intent(context, PairingNotificationService::class.java).apply {
            action = PairingNotificationService.ACTION_SUBMIT_CODE
            putExtra(PairingNotificationService.EXTRA_CODE, code)
            putExtra(
                PairingNotificationService.EXTRA_HOST,
                intent.getStringExtra(PairingNotificationService.EXTRA_HOST).orEmpty()
            )
            putExtra(
                PairingNotificationService.EXTRA_PORT,
                intent.getIntExtra(PairingNotificationService.EXTRA_PORT, 0)
            )
        }

        try {
            context.startForegroundService(serviceIntent)
        } catch (_: Throwable) {
            context.startService(serviceIntent)
        }
    }

    companion object {
        const val ACTION_INPUT = "com.myvision.naverclipautoswipe.PAIR_CODE_INPUT"
    }
}
