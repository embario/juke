package fm.juke.core.session

import fm.juke.core.testing.FakeAuthRepository
import fm.juke.core.testing.MainDispatcherRule
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AppSessionViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun emitsSignedOutThenSignedInBasedOnSessionFlow() = runTest {
        val auth = FakeAuthRepository()
        val viewModel = AppSessionViewModel(repository = auth)

        advanceUntilIdle()
        assertTrue(viewModel.uiState.value is AppSessionUiState.SignedOut)

        auth.setSession(SessionSnapshot("user", "token"))
        advanceUntilIdle()
        assertTrue(viewModel.uiState.value is AppSessionUiState.SignedIn)
    }
}
