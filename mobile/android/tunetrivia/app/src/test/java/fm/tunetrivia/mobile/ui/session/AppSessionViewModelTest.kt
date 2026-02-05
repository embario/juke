package fm.tunetrivia.mobile.ui.session

import fm.tunetrivia.mobile.data.local.SessionSnapshot
import fm.tunetrivia.mobile.testutil.FakeAuthRepository
import fm.tunetrivia.mobile.testutil.MainDispatcherRule
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
    fun `emits signed-out then signed-in based on session flow`() = runTest {
        val auth = FakeAuthRepository()
        val vm = AppSessionViewModel(repository = auth)

        advanceUntilIdle()
        assertTrue(vm.uiState.value is AppSessionUiState.SignedOut)

        auth.setSession(SessionSnapshot("user", "token"))
        advanceUntilIdle()
        assertTrue(vm.uiState.value is AppSessionUiState.SignedIn)
    }
}
