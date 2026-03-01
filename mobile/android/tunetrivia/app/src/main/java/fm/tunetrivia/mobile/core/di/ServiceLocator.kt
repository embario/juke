package fm.tunetrivia.mobile.core.di

import android.content.Context
import fm.tunetrivia.mobile.BuildConfig
import fm.tunetrivia.mobile.data.network.TuneTriviaApiService
import fm.tunetrivia.mobile.data.repository.TuneTriviaRepository
import fm.juke.core.di.CoreConfig
import fm.juke.core.di.CoreServiceLocator

object ServiceLocator {

    val apiService: TuneTriviaApiService by lazy {
        CoreServiceLocator.retrofit.create(TuneTriviaApiService::class.java)
    }

    val sessionStore get() = CoreServiceLocator.sessionStore

    val authRepository get() = CoreServiceLocator.authRepository

    val tuneTriviaRepository: TuneTriviaRepository by lazy {
        TuneTriviaRepository(apiService, authRepository)
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
}
