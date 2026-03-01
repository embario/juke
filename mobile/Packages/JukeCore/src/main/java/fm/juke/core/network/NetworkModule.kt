package fm.juke.core.network

import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory

object NetworkModule {

    val json: Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    fun buildOkHttpClient(isDebug: Boolean): OkHttpClient {
        val loggingInterceptor = HttpLoggingInterceptor().apply {
            level = if (isDebug) {
                HttpLoggingInterceptor.Level.BODY
            } else {
                HttpLoggingInterceptor.Level.BASIC
            }
        }
        return OkHttpClient.Builder()
            .addInterceptor(loggingInterceptor)
            .build()
    }

    fun buildRetrofit(baseUrl: String, client: OkHttpClient): Retrofit {
        val contentType = "application/json".toMediaType()
        return Retrofit.Builder()
            .baseUrl(normalizeUrl(baseUrl))
            .addConverterFactory(json.asConverterFactory(contentType))
            .client(client)
            .build()
    }

    fun normalizeUrl(rawUrl: String): String {
        val raw = rawUrl.trimEnd('/')
        return "$raw/"
    }
}
