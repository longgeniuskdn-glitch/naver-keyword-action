package com.myvision.naverclipautoswipe

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.util.Log
import java.net.NetworkInterface

class AdbMdns(
    context: Context,
    private val serviceType: String,
    private val callback: (String, Int) -> Unit
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
                        val host = info.host?.hostAddress.orEmpty()
                        if (host.isBlank() || info.port !in 1..65535) return

                        val isThisDevice = try {
                            NetworkInterface.getNetworkInterfaces().asSequence().any { ni ->
                                ni.inetAddresses.asSequence().any { addr -> addr.hostAddress == host }
                            }
                        } catch (_: Throwable) {
                            false
                        }

                        if (isThisDevice) {
                            serviceName = info.serviceName
                            Log.i(TAG, "Resolved $serviceType at $host:${info.port}")
                            callback(host, info.port)
                        }
                    }
                })
            } catch (_: Throwable) { }
        }

        override fun onServiceLost(serviceInfo: NsdServiceInfo) {
            if (serviceInfo.serviceName == serviceName) callback("", -1)
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

    companion object {
        const val TLS_CONNECT = "_adb-tls-connect._tcp"
        const val TLS_PAIRING = "_adb-tls-pairing._tcp"
        private const val TAG = "ClipAdbMdns"
    }
}
