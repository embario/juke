package fm.juke.mobile.ui.auth

import fm.juke.mobile.data.local.SessionSnapshot
import fm.juke.mobile.data.repository.AuthRepositoryContract
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

private class FakeAuthRepository : AuthRepositoryContract {
    private val sessionFlow = MutableStateFlow<SessionSnapshot?>(null)

    override val session: Flow<SessionSnapshot?> = sessionFlow

    override suspend fun login(username: String, password: String): Result<Unit> {
        return Result.success(Unit)
    }

    override suspend fun register(
        username: String,
        email: String,
        password: String,
        confirm: String,
    ): Result<String> {
        return Result.success("ok")
    }

    override suspend fun logout() {
        sessionFlow.value = null
    }

    override suspend fun currentSession(): SessionSnapshot? = sessionFlow.value
}

class AuthViewModelTest {
    @Test
    fun registrationDisabledLocksToLoginMode() {
        val viewModel = AuthViewModel(
            repository = FakeAuthRepository(),
            registrationDisabled = true,
        )

        assertTrue(viewModel.uiState.isRegistrationDisabled)
        assertEquals(AuthMode.LOGIN, viewModel.uiState.mode)

        viewModel.toggleMode()

        assertEquals(AuthMode.LOGIN, viewModel.uiState.mode)
        assertEquals(
            "Registration is temporarily disabled. Please try again later.",
            viewModel.uiState.error,
        )
    }
}
