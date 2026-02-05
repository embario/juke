package fm.tunetrivia.mobile.core.di

import android.content.Context
import fm.tunetrivia.mobile.BuildConfig
import fm.tunetrivia.mobile.data.local.SessionStore
import fm.tunetrivia.mobile.data.network.TuneTriviaApiService
import fm.tunetrivia.mobile.data.repository.AuthRepository
import fm.tunetrivia.mobile.data.repository.AuthRepositoryContract
import fm.tunetrivia.mobile.data.repository.TuneTriviaRepository
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory

object ServiceLocator {
    private lateinit var appContext: Context

    val json = Json {
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

    private val retrofit by lazy {
        val contentType = "application/json".toMediaType()
        Retrofit.Builder()
            .baseUrl(normalizedBaseUrl())
            .addConverterFactory(json.asConverterFactory(contentType))
            .client(okHttpClient)
            .build()
    }

    val apiService: TuneTriviaApiService by lazy {
        retrofit.create(TuneTriviaApiService::class.java)
    }

    val sessionStore: SessionStore by lazy {
        ensureInitialized()
        SessionStore(appContext)
    }

    val authRepository: AuthRepositoryContract by lazy {
        AuthRepository(apiService, sessionStore)
    }

    val tuneTriviaRepository: TuneTriviaRepository by lazy {
        TuneTriviaRepository(apiService, authRepository)
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

    private fun ensureInitialized() {
        check(::appContext.isInitialized) {
            "ServiceLocator.init(Context) must be called before accessing dependencies."
        }
    }
}
