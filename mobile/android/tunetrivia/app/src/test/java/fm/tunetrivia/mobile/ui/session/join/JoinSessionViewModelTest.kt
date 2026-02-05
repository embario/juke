package fm.tunetrivia.mobile.ui.session.join

import fm.tunetrivia.mobile.data.repository.TuneTriviaRepository
import fm.tunetrivia.mobile.testutil.FakeAuthRepository
import fm.tunetrivia.mobile.testutil.FakeTuneTriviaApiService
import fm.tunetrivia.mobile.testutil.MainDispatcherRule
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class JoinSessionViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `updateCode uppercases and truncates to six chars`() {
        val vm = JoinSessionViewModel(
            repository = TuneTriviaRepository(FakeTuneTriviaApiService(), FakeAuthRepository()),
        )

        vm.updateCode("ab12cd34")

        assertEquals("AB12CD", vm.uiState.value.code)
    }

    @Test
    fun `join validates code length and invokes callback on success`() = runTest {
        val vm = JoinSessionViewModel(
            repository = TuneTriviaRepository(FakeTuneTriviaApiService(), FakeAuthRepository()),
        )
        var joinedId: Int? = null

        vm.join(onJoined = { joinedId = it }, needsDisplayName = false)
        assertEquals("Please enter a 6-character code.", vm.uiState.value.error)

        vm.updateCode("ABC123")
        vm.join(onJoined = { joinedId = it }, needsDisplayName = false)
        advanceUntilIdle()

        assertEquals(1, joinedId)
    }
}
