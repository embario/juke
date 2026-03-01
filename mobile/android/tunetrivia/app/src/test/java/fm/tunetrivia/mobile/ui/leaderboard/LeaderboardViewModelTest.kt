package fm.tunetrivia.mobile.ui.leaderboard

import fm.tunetrivia.mobile.data.repository.TuneTriviaRepository
import fm.juke.core.testing.FakeAuthRepository
import fm.juke.core.testing.MainDispatcherRule
import fm.tunetrivia.mobile.testutil.FakeTuneTriviaApiService
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class LeaderboardViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `load populates leaderboard entries`() = runTest {
        val vm = LeaderboardViewModel(
            repository = TuneTriviaRepository(FakeTuneTriviaApiService(), FakeAuthRepository()),
        )

        advanceUntilIdle()

        assertFalse(vm.uiState.value.isLoading)
        assertEquals(1, vm.uiState.value.entries.size)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `load surfaces api failure`() = runTest {
        val api = FakeTuneTriviaApiService().apply { leaderboardError = IllegalStateException("down") }
        val vm = LeaderboardViewModel(
            repository = TuneTriviaRepository(api, FakeAuthRepository()),
        )

        advanceUntilIdle()

        assertFalse(vm.uiState.value.isLoading)
        assertTrue(vm.uiState.value.entries.isEmpty())
        assertEquals("down", vm.uiState.value.error)
    }
}
