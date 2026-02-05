package fm.tunetrivia.mobile.ui.session.game

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
}
