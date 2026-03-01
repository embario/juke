package fm.juke.core.auth

import fm.juke.core.testing.FakeAuthRepository
import fm.juke.core.testing.MainDispatcherRule
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AuthViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun registrationDisabledLocksToLoginMode() = runTest {
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

    @Test
    fun loginValidatesRequiredFields() = runTest {
        val viewModel = AuthViewModel(
            repository = FakeAuthRepository(),
            registrationDisabled = false,
        )

        viewModel.submit()
        assertEquals("Username is required.", viewModel.uiState.error)

        viewModel.updateUsername("user")
        viewModel.submit()
        assertEquals("Password is required.", viewModel.uiState.error)
    }

    @Test
    fun successfulLoginSetsSignedInMessage() = runTest {
        val viewModel = AuthViewModel(
            repository = FakeAuthRepository(),
            registrationDisabled = false,
        )

        viewModel.updateUsername("user")
        viewModel.updatePassword("password123")
        viewModel.submit()
        advanceUntilIdle()

        assertEquals("Signed in as user", viewModel.uiState.message)
        assertEquals("", viewModel.uiState.password)
    }
}
