package com.juke.shotclock.ui.auth

import com.juke.shotclock.BuildConfig
import com.juke.shotclock.core.di.ServiceLocator
import fm.juke.core.auth.AuthRepositoryContract
import fm.juke.core.auth.AuthViewModel as CoreAuthViewModel

class AuthViewModel(
    repository: AuthRepositoryContract = ServiceLocator.authRepository,
    registrationDisabled: Boolean = BuildConfig.DISABLE_REGISTRATION,
) : CoreAuthViewModel(repository, registrationDisabled)
