package com.myvision.naverclipautoswipe

import android.content.Context
import android.os.Build
import android.util.Base64
import android.sun.security.x509.*
import io.github.muntashirakon.adb.AbsAdbConnectionManager
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.PrivateKey
import java.security.SecureRandom
import java.security.cert.Certificate
import java.security.cert.CertificateFactory
import java.security.spec.PKCS8EncodedKeySpec
import java.util.Date
import java.util.Random

class AdbConnectionManager private constructor(private val context: Context) : AbsAdbConnectionManager() {
    companion object {
        @Volatile private var instance: AdbConnectionManager? = null
        fun getInstance(context: Context): AdbConnectionManager = instance ?: synchronized(this) {
            instance ?: AdbConnectionManager(context.applicationContext).also { instance = it }
        }
        private const val PREFS = "local_adb_keys"
        private const val KEY_PRIVATE = "private_key"
        private const val KEY_CERT = "certificate"
    }

    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private var privateKey: PrivateKey? = null
    private var certificate: Certificate? = null

    init {
        setApi(Build.VERSION.SDK_INT)
        loadOrGenerateKeys()
    }

    private fun loadOrGenerateKeys() {
        val priv = prefs.getString(KEY_PRIVATE, null)
        val cert = prefs.getString(KEY_CERT, null)
        if (priv != null && cert != null) {
            try {
                privateKey = KeyFactory.getInstance("RSA").generatePrivate(
                    PKCS8EncodedKeySpec(Base64.decode(priv, Base64.DEFAULT))
                )
                certificate = CertificateFactory.getInstance("X.509").generateCertificate(
                    Base64.decode(cert, Base64.DEFAULT).inputStream()
                )
                return
            } catch (_: Throwable) { }
        }
        generateKeys()
    }

    private fun generateKeys() {
        val generator = KeyPairGenerator.getInstance("RSA")
        generator.initialize(2048, SecureRandom.getInstance("SHA1PRNG"))
        val keyPair = generator.generateKeyPair()
        privateKey = keyPair.private

        val subject = X500Name("CN=MyVision Clip AutoSwipe")
        val algorithm = "SHA512withRSA"
        val notBefore = Date()
        val notAfter = Date(System.currentTimeMillis() + 3650L * 24L * 60L * 60L * 1000L)
        val extensions = CertificateExtensions()
        extensions.set("SubjectKeyIdentifier", SubjectKeyIdentifierExtension(KeyIdentifier(keyPair.public).identifier))
        extensions.set("PrivateKeyUsage", PrivateKeyUsageExtension(notBefore, notAfter))

        val info = X509CertInfo()
        info.set("version", CertificateVersion(2))
        info.set("serialNumber", CertificateSerialNumber(Random().nextInt() and Integer.MAX_VALUE))
        info.set("algorithmID", CertificateAlgorithmId(AlgorithmId.get(algorithm)))
        info.set("subject", CertificateSubjectName(subject))
        info.set("key", CertificateX509Key(keyPair.public))
        info.set("validity", CertificateValidity(notBefore, notAfter))
        info.set("issuer", CertificateIssuerName(subject))
        info.set("extensions", extensions)

        val cert = X509CertImpl(info)
        cert.sign(privateKey, algorithm)
        certificate = cert

        prefs.edit()
            .putString(KEY_PRIVATE, Base64.encodeToString(privateKey!!.encoded, Base64.NO_WRAP))
            .putString(KEY_CERT, Base64.encodeToString(certificate!!.encoded, Base64.NO_WRAP))
            .apply()
    }

    public override fun getPrivateKey(): PrivateKey = privateKey!!
    public override fun getCertificate(): Certificate = certificate!!
    public override fun getDeviceName(): String = "MyVision-Clip-AutoSwipe"
}
