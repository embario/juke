package fm.tunetrivia.mobile.data.repository

import fm.juke.core.session.SessionSnapshot
import fm.juke.core.testing.FakeAuthRepository
import fm.tunetrivia.mobile.testutil.FakeTuneTriviaApiService
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class TuneTriviaRepositoryTest {
    @Test
    fun `getMySessions fails when no auth session`() = runTest {
        val auth = FakeAuthRepository()
        val api = FakeTuneTriviaApiService()
        val repo = TuneTriviaRepository(api, auth)

        val result = repo.getMySessions()

        assertTrue(result.isFailure)
    }

    @Test
    fun `joinSession sends null token for guests`() = runTest {
        val auth = FakeAuthRepository()
        val api = FakeTuneTriviaApiService()
        val repo = TuneTriviaRepository(api, auth)

        val result = repo.joinSession("ABC123", "Guest")

        assertTrue(result.isSuccess)
        assertNull(api.lastJoinToken)
        assertEquals("ABC123", api.lastJoinRequest?.code)
    }

    @Test
    fun `createSession passes bearer token and maps response`() = runTest {
        val auth = FakeAuthRepository().apply {
            setSession(SessionSnapshot(username = "host", token = "secret"))
        }
        val api = FakeTuneTriviaApiService()
        val repo = TuneTriviaRepository(api, auth)

        val result = repo.createSession(
            name = "Game Night",
            mode = "party",
            maxSongs = 12,
            secondsPerSong = 20,
            enableTrivia = true,
        )

        assertTrue(result.isSuccess)
        assertEquals("Token secret", api.lastAuthToken)
        assertEquals("Game Night", api.lastCreateRequest?.name)
        assertEquals(12, api.lastCreateRequest?.maxSongs)
    }

    @Test
    fun `submitGuess forwards payload and handles api failure`() = runTest {
        val auth = FakeAuthRepository().apply {
            setSession(SessionSnapshot(username = "u", token = "secret"))
        }
        val api = FakeTuneTriviaApiService()
        val repo = TuneTriviaRepository(api, auth)

        val ok = repo.submitGuess(roundId = 44, songGuess = "Song", artistGuess = "Artist")
        assertTrue(ok.isSuccess)
        assertEquals("Song", api.lastSubmitGuessRequest?.songGuess)

        api.submitGuessError = IllegalStateException("boom")
        val failure = repo.submitGuess(roundId = 44, songGuess = "Song", artistGuess = "Artist")
        assertFalse(failure.isSuccess)
    }
}
