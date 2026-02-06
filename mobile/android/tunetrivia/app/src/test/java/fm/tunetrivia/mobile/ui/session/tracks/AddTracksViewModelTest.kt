package fm.tunetrivia.mobile.ui.session.tracks

import fm.tunetrivia.mobile.data.local.SessionSnapshot
import fm.tunetrivia.mobile.data.repository.TuneTriviaRepository
import fm.tunetrivia.mobile.testutil.FakeAuthRepository
import fm.tunetrivia.mobile.testutil.FakeTuneTriviaApiService
import fm.tunetrivia.mobile.testutil.MainDispatcherRule
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AddTracksViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `search ignores blank query`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("host", "token")) }
        val vm = AddTracksViewModel(repository = TuneTriviaRepository(FakeTuneTriviaApiService(), auth))

        vm.updateQuery("   ")
        vm.search()
        advanceUntilIdle()

        assertTrue(vm.uiState.value.results.isEmpty())
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `search loads track results`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("host", "token")) }
        val vm = AddTracksViewModel(repository = TuneTriviaRepository(FakeTuneTriviaApiService(), auth))

        vm.updateQuery("song")
        vm.search()
        advanceUntilIdle()

        assertEquals(1, vm.uiState.value.results.size)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `addTrack removes item and sets success message`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("host", "token")) }
        val api = FakeTuneTriviaApiService()
        val vm = AddTracksViewModel(repository = TuneTriviaRepository(api, auth))

        vm.updateQuery("song")
        vm.search()
        advanceUntilIdle()

        val track = vm.uiState.value.results.first()
        vm.addTrack(sessionId = 1, track = track)
        advanceUntilIdle()

        assertTrue(vm.uiState.value.results.isEmpty())
        assertEquals("Added \"${track.name}\"", vm.uiState.value.success)
    }

    @Test
    fun `autoFill invokes callback and reports count`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("host", "token")) }
        val vm = AddTracksViewModel(repository = TuneTriviaRepository(FakeTuneTriviaApiService(), auth))
        var callbackCalled = false

        vm.autoFill(sessionId = 1, count = 3) { callbackCalled = true }
        advanceUntilIdle()

        assertTrue(callbackCalled)
        assertEquals("Added 3 tracks", vm.uiState.value.success)
    }

    @Test
    fun `autoFill is ignored while a track add is in progress`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("host", "token")) }
        val api = FakeTuneTriviaApiService().apply { addTrackDelayMs = 1_000 }
        val vm = AddTracksViewModel(repository = TuneTriviaRepository(api, auth))
        var autoFillCallbackCalled = false

        vm.updateQuery("song")
        vm.search()
        advanceUntilIdle()

        vm.addTrack(sessionId = 1, track = vm.uiState.value.results.first())
        vm.autoFill(sessionId = 1, count = 3) { autoFillCallbackCalled = true }
        advanceUntilIdle()

        assertTrue(vm.uiState.value.success?.startsWith("Added") == true)
        assertTrue(vm.uiState.value.isAddingTrack.not())
        assertTrue(autoFillCallbackCalled.not())
    }

    @Test
    fun `search sets error when auth missing`() = runTest {
        val vm = AddTracksViewModel(
            repository = TuneTriviaRepository(FakeTuneTriviaApiService(), FakeAuthRepository()),
        )

        vm.updateQuery("song")
        vm.search()
        advanceUntilIdle()

        assertEquals("No active session token", vm.uiState.value.error)
    }
}
