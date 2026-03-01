package fm.juke.mobile.core.di

import android.content.Context
import fm.juke.mobile.BuildConfig
import fm.juke.mobile.data.local.JukeSessionStore
import fm.juke.mobile.data.repository.ProfileRepository
import fm.juke.core.auth.AuthRepository
import fm.juke.core.auth.AuthRepositoryContract
import fm.juke.core.catalog.CatalogRepository
import fm.juke.core.di.CoreConfig
import fm.juke.core.di.CoreServiceLocator
import fm.juke.core.network.NetworkModule
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.dnsoverhttps.DnsOverHttps
import okhttp3.Dns
import coil.ImageLoader
import android.os.Build
import java.net.InetAddress

object ServiceLocator {

    val imageLoader: ImageLoader by lazy {
        val baseClient = CoreServiceLocator.okHttpClient.newBuilder().build()
        val client = if (BuildConfig.DEBUG && !isEmulator()) {
            val bootstrap = listOf(
                InetAddress.getByName("8.8.8.8"),
                InetAddress.getByName("8.8.4.4"),
                InetAddress.getByName("1.1.1.1"),
                InetAddress.getByName("1.0.0.1"),
            )
            val bootstrapDns = object : Dns {
                override fun lookup(hostname: String): List<InetAddress> {
                    val normalized = hostname.trimEnd('.').lowercase()
                    return if (normalized == "dns.google") {
                        bootstrap
                    } else {
                        Dns.SYSTEM.lookup(hostname)
                    }
                }
            }
            val dohClient = baseClient.newBuilder()
                .dns(bootstrapDns)
                .build()
            val doh = DnsOverHttps.Builder()
                .client(dohClient)
                .url("https://dns.google/dns-query".toHttpUrl())
                .build()
            baseClient.newBuilder()
                .dns(doh)
                .build()
        } else {
            baseClient
        }
        ImageLoader.Builder(CoreServiceLocator.appContext)
            .okHttpClient(client)
            .build()
    }

    // Juke overrides sessionStore with JukeSessionStore (adds onboarding).
    val sessionStore: JukeSessionStore by lazy {
        JukeSessionStore(CoreServiceLocator.appContext)
    }

    val authRepository: AuthRepositoryContract by lazy {
        AuthRepository(CoreServiceLocator.coreApiService, sessionStore)
    }

    val profileRepository: ProfileRepository by lazy {
        ProfileRepository(CoreServiceLocator.coreApiService, sessionStore)
    }

    val catalogRepository: CatalogRepository by lazy {
        CatalogRepository(CoreServiceLocator.coreApiService, sessionStore)
    }

    fun init(context: Context) {
        CoreServiceLocator.init(
            context,
            CoreConfig(
                backendUrl = BuildConfig.BACKEND_URL,
                isDebug = BuildConfig.DEBUG,
            ),
        )
    }

    internal fun normalizedBaseUrl(rawBaseUrl: String = BuildConfig.BACKEND_URL): String =
        NetworkModule.normalizeUrl(rawBaseUrl)

    internal fun normalizedFrontendUrl(rawFrontendUrl: String = BuildConfig.FRONTEND_URL): String =
        NetworkModule.normalizeUrl(rawFrontendUrl)

    private fun isEmulator(): Boolean {
        val fingerprint = Build.FINGERPRINT
        return fingerprint.startsWith("generic") ||
            fingerprint.startsWith("unknown") ||
            Build.MODEL.contains("google_sdk", ignoreCase = true) ||
            Build.MODEL.contains("Emulator", ignoreCase = true) ||
            Build.MODEL.contains("Android SDK built for", ignoreCase = true) ||
            Build.MANUFACTURER.contains("Genymotion", ignoreCase = true) ||
            (Build.BRAND.startsWith("generic") && Build.DEVICE.startsWith("generic")) ||
            Build.PRODUCT.contains("sdk", ignoreCase = true) ||
            Build.PRODUCT.contains("emulator", ignoreCase = true) ||
            Build.PRODUCT.contains("simulator", ignoreCase = true)
    }
}
