package fm.tunetrivia.mobile.ui.session.lobby

import fm.juke.core.session.SessionSnapshot
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
class SessionLobbyViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `load populates session detail`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("host", "token")) }
        val vm = SessionLobbyViewModel(
            repository = TuneTriviaRepository(FakeTuneTriviaApiService(), auth),
        )

        vm.load(sessionId = 1)
        advanceUntilIdle()

        assertFalse(vm.uiState.value.isLoading)
        assertEquals(1, vm.uiState.value.session?.id)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `startGame invokes callback on success`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("host", "token")) }
        val vm = SessionLobbyViewModel(
            repository = TuneTriviaRepository(FakeTuneTriviaApiService(), auth),
        )
        var started = false

        vm.startGame(sessionId = 1) { started = true }
        advanceUntilIdle()

        assertTrue(started)
        assertFalse(vm.uiState.value.isStarting)
    }

    @Test
    fun `startGame shows error when auth missing`() = runTest {
        val vm = SessionLobbyViewModel(
            repository = TuneTriviaRepository(FakeTuneTriviaApiService(), FakeAuthRepository()),
        )

        vm.startGame(sessionId = 1) {}
        advanceUntilIdle()

        assertEquals("No active session token", vm.uiState.value.error)
        assertFalse(vm.uiState.value.isStarting)
    }

    @Test
    fun `addPlayer ignores blank names`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("host", "token")) }
        val vm = SessionLobbyViewModel(
            repository = TuneTriviaRepository(FakeTuneTriviaApiService(), auth),
        )
        var callbackCalled = false

        vm.addPlayer(sessionId = 1, name = "   ") { callbackCalled = true }
        advanceUntilIdle()

        assertFalse(callbackCalled)
    }
}
