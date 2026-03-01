package fm.juke.mobile.ui.auth

import fm.juke.mobile.BuildConfig
import fm.juke.mobile.core.di.ServiceLocator
import fm.juke.core.auth.AuthRepositoryContract
import fm.juke.core.auth.AuthViewModel as CoreAuthViewModel

class AuthViewModel(
    repository: AuthRepositoryContract = ServiceLocator.authRepository,
    registrationDisabled: Boolean = BuildConfig.DISABLE_REGISTRATION,
) : CoreAuthViewModel(repository, registrationDisabled)
