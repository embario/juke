package fm.tunetrivia.mobile.ui.session.create

import fm.tunetrivia.mobile.data.local.SessionSnapshot
import fm.tunetrivia.mobile.data.repository.TuneTriviaRepository
import fm.tunetrivia.mobile.testutil.FakeAuthRepository
import fm.tunetrivia.mobile.testutil.FakeTuneTriviaApiService
import fm.tunetrivia.mobile.testutil.MainDispatcherRule
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class CreateSessionViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `create requires non-empty name`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("u", "t")) }
        val repo = TuneTriviaRepository(FakeTuneTriviaApiService(), auth)
        val vm = CreateSessionViewModel(repository = repo)

        vm.create {}

        assertEquals("Game name is required.", vm.uiState.value.error)
    }

    @Test
    fun `successful create invokes callback with session id`() = runTest {
        val auth = FakeAuthRepository().apply { setSession(SessionSnapshot("u", "t")) }
        val api = FakeTuneTriviaApiService()
        val repo = TuneTriviaRepository(api, auth)
        val vm = CreateSessionViewModel(repository = repo)
        var createdId: Int? = null

        vm.updateName("Game")
        vm.create { createdId = it }
        advanceUntilIdle()

        assertEquals(api.createSessionResult.id, createdId)
        assertTrue(vm.uiState.value.error == null)
    }
}
