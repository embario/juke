package fm.juke.mobile.core.di

import android.content.Context
import fm.juke.mobile.BuildConfig
import fm.juke.mobile.data.local.SessionStore
import fm.juke.mobile.data.network.JukeApiService
import fm.juke.mobile.data.repository.AuthRepository
import fm.juke.mobile.data.repository.AuthRepositoryContract
import fm.juke.mobile.data.repository.CatalogRepository
import fm.juke.mobile.data.repository.ProfileRepository
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.dnsoverhttps.DnsOverHttps
import okhttp3.Dns
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import coil.ImageLoader
import java.net.InetAddress
import android.os.Build

object ServiceLocator {
    private lateinit var appContext: Context

    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    private val loggingInterceptor = HttpLoggingInterceptor().apply {
        level = if (BuildConfig.DEBUG) {
            HttpLoggingInterceptor.Level.BODY
        } else {
            HttpLoggingInterceptor.Level.BASIC
        }
    }

    private val okHttpClient by lazy {
        OkHttpClient.Builder()
            .addInterceptor(loggingInterceptor)
            .build()
    }

    val imageLoader: ImageLoader by lazy {
        ensureInitialized()
        val baseClient = okHttpClient.newBuilder().build()
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
        ImageLoader.Builder(appContext)
            .okHttpClient(client)
            .build()
    }

    private val retrofit by lazy {
        val contentType = "application/json".toMediaType()
        Retrofit.Builder()
            .baseUrl(normalizedBaseUrl())
            .addConverterFactory(json.asConverterFactory(contentType))
            .client(okHttpClient)
            .build()
    }

    val apiService: JukeApiService by lazy {
        retrofit.create(JukeApiService::class.java)
    }

    val sessionStore: SessionStore by lazy {
        ensureInitialized()
        SessionStore(appContext)
    }

    val authRepository: AuthRepositoryContract by lazy {
        AuthRepository(apiService, sessionStore)
    }

    val profileRepository: ProfileRepository by lazy {
        ProfileRepository(apiService, sessionStore)
    }

    val catalogRepository: CatalogRepository by lazy {
        CatalogRepository(apiService, sessionStore)
    }

    fun init(context: Context) {
        if (!::appContext.isInitialized) {
            appContext = context.applicationContext
        }
    }

    internal fun normalizedBaseUrl(rawBaseUrl: String = BuildConfig.BACKEND_URL): String {
        val raw = rawBaseUrl.trimEnd('/')
        return "$raw/"
    }

    internal fun normalizedFrontendUrl(rawFrontendUrl: String = BuildConfig.FRONTEND_URL): String {
        val raw = rawFrontendUrl.trimEnd('/')
        return "$raw/"
    }

    private fun ensureInitialized() {
        check(::appContext.isInitialized) {
            "ServiceLocator.init(Context) must be called before accessing dependencies."
        }
    }

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
