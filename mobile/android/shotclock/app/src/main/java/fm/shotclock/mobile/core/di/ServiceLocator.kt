package fm.shotclock.mobile.core.di

import android.content.Context
import fm.shotclock.mobile.BuildConfig
import fm.shotclock.mobile.data.network.ShotClockApiService
import fm.shotclock.mobile.data.repository.CatalogRepository
import fm.shotclock.mobile.data.repository.PowerHourRepository
import fm.shotclock.mobile.data.repository.ProfileRepository
import fm.juke.core.di.CoreConfig
import fm.juke.core.di.CoreServiceLocator

object ServiceLocator {

    val apiService: ShotClockApiService by lazy {
        CoreServiceLocator.retrofit.create(ShotClockApiService::class.java)
    }

    val sessionStore get() = CoreServiceLocator.sessionStore

    val authRepository get() = CoreServiceLocator.authRepository

    val profileRepository: ProfileRepository by lazy {
        ProfileRepository(apiService, sessionStore)
    }

    val catalogRepository: CatalogRepository by lazy {
        CatalogRepository(apiService, sessionStore)
    }

    val powerHourRepository: PowerHourRepository by lazy {
        PowerHourRepository(apiService, sessionStore)
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
