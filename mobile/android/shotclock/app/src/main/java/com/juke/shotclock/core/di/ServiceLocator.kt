package com.juke.shotclock.core.di

import android.content.Context
import com.juke.shotclock.BuildConfig
import com.juke.shotclock.data.network.ShotClockApiService
import com.juke.shotclock.data.repository.CatalogRepository
import com.juke.shotclock.data.repository.PowerHourRepository
import com.juke.shotclock.data.repository.ProfileRepository
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
