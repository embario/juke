package fm.tunetrivia.mobile.ui.session.home

import fm.tunetrivia.mobile.data.local.SessionSnapshot
import fm.tunetrivia.mobile.data.repository.TuneTriviaRepository
import fm.tunetrivia.mobile.testutil.FakeAuthRepository
import fm.tunetrivia.mobile.testutil.FakeTuneTriviaApiService
import fm.tunetrivia.mobile.testutil.MainDispatcherRule
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
class HomeViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `loads sessions on init`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("host", "token")) }
        val api = FakeTuneTriviaApiService()
        val vm = HomeViewModel(repository = TuneTriviaRepository(api, auth))

        advanceUntilIdle()

        assertFalse(vm.uiState.value.isLoading)
        assertEquals(1, vm.uiState.value.sessions.size)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `loadSessions surfaces error when repository fails`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("host", "token")) }
        val api = FakeTuneTriviaApiService().apply { mySessionsError = IllegalStateException("boom") }
        val vm = HomeViewModel(repository = TuneTriviaRepository(api, auth))

        advanceUntilIdle()

        assertFalse(vm.uiState.value.isLoading)
        assertTrue(vm.uiState.value.sessions.isEmpty())
        assertEquals("boom", vm.uiState.value.error)
    }
}
