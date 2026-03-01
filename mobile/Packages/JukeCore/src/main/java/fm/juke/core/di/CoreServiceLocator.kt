package fm.juke.core.di

import android.content.Context
import fm.juke.core.auth.AuthRepository
import fm.juke.core.auth.AuthRepositoryContract
import fm.juke.core.network.CoreApiService
import fm.juke.core.network.NetworkModule
import fm.juke.core.session.SessionStore
import okhttp3.OkHttpClient
import retrofit2.Retrofit

object CoreServiceLocator {
    private lateinit var _appContext: Context
    private lateinit var _config: CoreConfig

    val appContext: Context get() = _appContext
    val config: CoreConfig get() = _config

    val okHttpClient: OkHttpClient by lazy {
        NetworkModule.buildOkHttpClient(_config.isDebug)
    }

    val retrofit: Retrofit by lazy {
        NetworkModule.buildRetrofit(_config.backendUrl, okHttpClient)
    }

    val coreApiService: CoreApiService by lazy {
        retrofit.create(CoreApiService::class.java)
    }

    val sessionStore: SessionStore by lazy {
        ensureInitialized()
        SessionStore(_appContext)
    }

    val authRepository: AuthRepositoryContract by lazy {
        AuthRepository(coreApiService, sessionStore)
    }

    fun init(context: Context, config: CoreConfig) {
        if (!::_appContext.isInitialized) {
            _appContext = context.applicationContext
            _config = config
        }
    }

    fun ensureInitialized() {
        check(::_appContext.isInitialized) {
            "CoreServiceLocator.init() must be called before accessing dependencies."
        }
    }
}
