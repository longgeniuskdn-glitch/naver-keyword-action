package com.myvision.naverclipautoswipe

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.util.Log
import java.io.IOException
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.net.ServerSocket

class AdbMdns(
    context: Context,
    private val serviceType: String,
    private val callback: (Int) -> Unit
) {
    private val manager = context.getSystemService(NsdManager::class.java)
    private var running = false
    private var registered = false
    private var serviceName: String? = null

    private val listener = object : NsdManager.DiscoveryListener {
        override fun onDiscoveryStarted(serviceType: String) {
            registered = true
            if (!running) unregister()
        }
        override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
            Log.w(TAG, "Discovery start failed: $errorCode")
        }
        override fun onDiscoveryStopped(serviceType: String) { registered = false }
        override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) { registered = false }
        override fun onServiceFound(serviceInfo: NsdServiceInfo) {
            try {
                manager.resolveService(serviceInfo, object : NsdManager.ResolveListener {
                    override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) = Unit
                    override fun onServiceResolved(info: NsdServiceInfo) {
                        if (!running) return
                        val isLocal = NetworkInterface.getNetworkInterfaces().asSequence().any { ni ->
                            ni.inetAddresses.asSequence().any { it.hostAddress == info.host.hostAddress }
                        }
                        if (isLocal && isPortListening(info.port)) {
                            serviceName = info.serviceName
                            callback(info.port)
                        }
                    }
                })
            } catch (_: Throwable) { }
        }
        override fun onServiceLost(serviceInfo: NsdServiceInfo) {
            if (serviceInfo.serviceName == serviceName) callback(-1)
        }
    }

    fun start() {
        if (running) return
        running = true
        try { manager.discoverServices(serviceType, NsdManager.PROTOCOL_DNS_SD, listener) }
        catch (_: Throwable) { }
    }

    fun stop() {
        running = false
        unregister()
    }

    private fun unregister() {
        if (!registered) return
        registered = false
        try { manager.stopServiceDiscovery(listener) } catch (_: Throwable) { }
    }

    private fun isPortListening(port: Int): Boolean = try {
        ServerSocket().use { it.bind(InetSocketAddress("127.0.0.1", port), 1) }
        false
    } catch (_: IOException) { true }

    companion object {
        const val TLS_CONNECT = "_adb-tls-connect._tcp"
        const val TLS_PAIRING = "_adb-tls-pairing._tcp"
        private const val TAG = "ClipAdbMdns"
    }
}
