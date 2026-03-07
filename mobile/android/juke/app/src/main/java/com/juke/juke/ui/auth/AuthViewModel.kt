package com.juke.juke.ui.auth

import com.juke.juke.BuildConfig
import com.juke.juke.core.di.ServiceLocator
import fm.juke.core.auth.AuthRepositoryContract
import fm.juke.core.auth.AuthViewModel as CoreAuthViewModel

class AuthViewModel(
    repository: AuthRepositoryContract = ServiceLocator.authRepository,
    registrationDisabled: Boolean = BuildConfig.DISABLE_REGISTRATION,
) : CoreAuthViewModel(repository, registrationDisabled)
