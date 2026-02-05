package fm.tunetrivia.mobile.ui.auth

import fm.tunetrivia.mobile.testutil.FakeAuthRepository
import fm.tunetrivia.mobile.testutil.MainDispatcherRule
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
    fun `login validates required fields`() = runTest {
        val vm = AuthViewModel(repository = FakeAuthRepository(), registrationDisabled = false)

        vm.submit()
        assertEquals("Username is required.", vm.uiState.error)

        vm.updateUsername("user")
        vm.submit()
        assertEquals("Password is required.", vm.uiState.error)
    }

    @Test
    fun `successful login sets signed-in message`() = runTest {
        val vm = AuthViewModel(repository = FakeAuthRepository(), registrationDisabled = false)

        vm.updateUsername("user")
        vm.updatePassword("password123")
        vm.submit()
        advanceUntilIdle()

        assertEquals("Signed in as user", vm.uiState.message)
        assertEquals("", vm.uiState.password)
    }

    @Test
    fun `registration disabled blocks toggling and registration`() = runTest {
        val vm = AuthViewModel(repository = FakeAuthRepository(), registrationDisabled = true)

        vm.toggleMode()
        assertTrue(vm.uiState.error?.contains("temporarily disabled") == true)
    }
}
