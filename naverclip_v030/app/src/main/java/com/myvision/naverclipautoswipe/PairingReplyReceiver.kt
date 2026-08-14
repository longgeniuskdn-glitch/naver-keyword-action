package com.myvision.naverclipautoswipe

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.RemoteInput

class PairingReplyReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            ACTION_INPUT -> {
                val code = RemoteInput.getResultsFromIntent(intent)?.getCharSequence(KEY_CODE)?.toString().orEmpty()
                val port = intent.getIntExtra(EXTRA_PORT, 0)
                val serviceIntent = Intent(context, PairingService::class.java).apply {
                    action = PairingService.ACTION_SUBMIT
                    putExtra(PairingService.EXTRA_CODE, code)
                    putExtra(PairingService.EXTRA_PORT, port)
                }
                context.startForegroundService(serviceIntent)
            }
            ACTION_CANCEL -> context.stopService(Intent(context, PairingService::class.java))
        }
    }

    companion object {
        const val KEY_CODE = "pairing_code_reply"
        const val EXTRA_PORT = "pairing_port"
        const val ACTION_INPUT = "com.myvision.naverclipautoswipe.PAIR_CODE"
        const val ACTION_CANCEL = "com.myvision.naverclipautoswipe.PAIR_CANCEL"
    }
}
