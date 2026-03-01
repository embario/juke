package fm.tunetrivia.mobile.ui.auth

import fm.tunetrivia.mobile.BuildConfig
import fm.tunetrivia.mobile.core.di.ServiceLocator
import fm.juke.core.auth.AuthRepositoryContract
import fm.juke.core.auth.AuthViewModel as CoreAuthViewModel

class AuthViewModel(
    repository: AuthRepositoryContract = ServiceLocator.authRepository,
    registrationDisabled: Boolean = BuildConfig.DISABLE_REGISTRATION,
) : CoreAuthViewModel(repository, registrationDisabled)
