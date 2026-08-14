package com.myvision.naverclipautoswipe

import android.content.Context
import io.github.muntashirakon.adb.AdbStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull

object AdbEngine {
    private val codeRegex = Regex("\\d{6}")

    suspend fun pair(
        context: Context,
        detectedHostRaw: String,
        codeRaw: String,
        port: Int
    ): Result<Boolean> = withContext(Dispatchers.IO) {
        val detectedHost = detectedHostRaw.trim()
        val code = codeRaw.trim()
        if (!codeRegex.matches(code)) return@withContext Result.failure(Exception("6자리 페어링 코드를 입력해주세요."))
        if (port !in 1..65535) return@withContext Result.failure(Exception("페어링 포트를 찾지 못했습니다."))

        val candidates = linkedSetOf<String>().apply {
            add("127.0.0.1")
            if (detectedHost.isNotBlank()) add(detectedHost)
            add("::1")
        }.toList()

        val failures = mutableListOf<String>()
        val manager = AdbConnectionManager.getInstance(context)

        for (host in candidates) {
            try {
                val ok = withTimeoutOrNull(10_000L) { manager.pair(host, port, code) }
                when (ok) {
                    true -> {
                        context.getSharedPreferences("local_adb_route", Context.MODE_PRIVATE)
                            .edit().putString("last_pair_host", host).apply()
                        return@withContext Result.success(true)
                    }
                    false -> return@withContext Result.failure(
                        Exception("$host:$port 에 연결됐지만 코드가 거부되었습니다. 새 코드를 받아 다시 시도해주세요.")
                    )
                    null -> return@withContext Result.failure(
                        Exception("$host:$port 페어링 응답이 없어 시간이 초과되었습니다.")
                    )
                }
            } catch (t: Throwable) {
                failures += "$host=${t.javaClass.simpleName}"
            }
        }

        Result.failure(
            Exception("페어링 포트에 연결하지 못했습니다. 시도: ${failures.joinToString(", ")}")
        )
    }

    suspend fun isReady(context: Context): Boolean = withContext(Dispatchers.IO) {
        var stream: AdbStream? = null
        try {
            val manager = AdbConnectionManager.getInstance(context)
            if (!manager.autoConnect(context, 5000)) return@withContext false
            stream = manager.openStream("shell:echo myvision_ok")
            val input = stream.openInputStream()
            val buffer = ByteArray(128)
            var waited = 0
            while (waited < 3500) {
                if (input.available() > 0) {
                    val n = input.read(buffer)
                    if (n > 0 && String(buffer, 0, n).contains("myvision_ok")) return@withContext true
                }
                delay(100)
                waited += 100
            }
            false
        } catch (_: Throwable) {
            false
        } finally {
            try { stream?.close() } catch (_: Throwable) { }
        }
    }

    suspend fun runShell(context: Context, command: String): Result<String> = withContext(Dispatchers.IO) {
        var stream: AdbStream? = null
        try {
            val manager = AdbConnectionManager.getInstance(context)
            if (!manager.autoConnect(context, 8000)) return@withContext Result.failure(Exception("로컬 ADB 연결 실패"))
            stream = manager.openStream("shell:$command")
            val input = stream.openInputStream()
            val output = StringBuilder()
            val buffer = ByteArray(512)
            var waited = 0
            while (waited < 1800) {
                if (input.available() > 0) {
                    val n = input.read(buffer)
                    if (n <= 0) break
                    output.append(String(buffer, 0, n))
                } else {
                    delay(80)
                    waited += 80
                }
            }
            Result.success(output.toString().trim())
        } catch (t: Throwable) {
            Result.failure(t)
        } finally {
            try { stream?.close() } catch (_: Throwable) { }
        }
    }
}
