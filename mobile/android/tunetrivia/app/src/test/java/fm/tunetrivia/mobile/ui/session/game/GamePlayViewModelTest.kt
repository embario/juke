package fm.tunetrivia.mobile.ui.session.game

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
class GamePlayViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `load populates session`() = runTest {
        val vm = GamePlayViewModel(
            repository = TuneTriviaRepository(FakeTuneTriviaApiService(), FakeAuthRepository()),
        )

        vm.load(sessionId = 1)
        advanceUntilIdle()

        assertFalse(vm.uiState.value.isLoading)
        assertEquals(1, vm.uiState.value.session?.id)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `submitGuess invokes callback and clears submitting flag`() = runTest {
        val vm = GamePlayViewModel(
            repository = TuneTriviaRepository(FakeTuneTriviaApiService(), FakeAuthRepository()),
        )
        var callbackCalled = false

        vm.submitGuess(roundId = 1, song = "Song A", artist = "Artist A") { callbackCalled = true }
        advanceUntilIdle()

        assertTrue(callbackCalled)
        assertFalse(vm.uiState.value.isSubmittingGuess)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `submitTrivia stores trivia result and invokes callback`() = runTest {
        val vm = GamePlayViewModel(
            repository = TuneTriviaRepository(FakeTuneTriviaApiService(), FakeAuthRepository()),
        )
        var callbackCalled = false

        vm.submitTrivia(roundId = 1, answer = "A") { callbackCalled = true }
        advanceUntilIdle()

        assertTrue(callbackCalled)
        assertFalse(vm.uiState.value.isSubmittingTrivia)
        assertEquals(1, vm.uiState.value.triviaResult?.pointsEarned)
    }

    @Test
    fun `nextRound clears trivia result on success`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("host", "token")) }
        val vm = GamePlayViewModel(
            repository = TuneTriviaRepository(FakeTuneTriviaApiService(), auth),
        )

        vm.submitTrivia(roundId = 1, answer = "A") {}
        advanceUntilIdle()
        assertTrue(vm.uiState.value.triviaResult != null)

        vm.nextRound(sessionId = 1)
        advanceUntilIdle()

        assertFalse(vm.uiState.value.isAdvancing)
        assertNull(vm.uiState.value.triviaResult)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `nextRound sets error when auth missing`() = runTest {
        val vm = GamePlayViewModel(
            repository = TuneTriviaRepository(FakeTuneTriviaApiService(), FakeAuthRepository()),
        )

        vm.nextRound(sessionId = 1)
        advanceUntilIdle()

        assertFalse(vm.uiState.value.isAdvancing)
        assertEquals("No active session token", vm.uiState.value.error)
    }

    @Test
    fun `endGame toggles ending state off after success`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("host", "token")) }
        val vm = GamePlayViewModel(
            repository = TuneTriviaRepository(FakeTuneTriviaApiService(), auth),
        )

        vm.endGame(sessionId = 1)
        advanceUntilIdle()

        assertFalse(vm.uiState.value.isEnding)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `awardPoints tracks awarding player and invokes success callback`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("host", "token")) }
        val vm = GamePlayViewModel(
            repository = TuneTriviaRepository(FakeTuneTriviaApiService(), auth),
        )
        var success: Boolean? = null

        vm.awardPoints(playerId = 7, points = 100) { success = it }
        advanceUntilIdle()

        assertEquals(true, success)
        assertNull(vm.uiState.value.awardingPlayerId)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `awardPoints surfaces error and invokes failure callback`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("host", "token")) }
        val api = FakeTuneTriviaApiService().apply { awardPointsError = IllegalStateException("award failed") }
        val vm = GamePlayViewModel(
            repository = TuneTriviaRepository(api, auth),
        )
        var success: Boolean? = null

        vm.awardPoints(playerId = 7, points = 100) { success = it }
        advanceUntilIdle()

        assertEquals(false, success)
        assertNull(vm.uiState.value.awardingPlayerId)
        assertEquals("award failed", vm.uiState.value.error)
    }
}
