package fm.tunetrivia.mobile.model

import fm.tunetrivia.mobile.testutil.TestFixtures
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TuneTriviaModelsTest {
    @Test
    fun `maps active and ended statuses correctly`() {
        val active = TestFixtures.sessionDto(status = "active").toModel()
        val ended = TestFixtures.sessionDto(status = "ended").toModel()

        assertEquals(SessionStatus.PLAYING, active.status)
        assertEquals(SessionStatus.FINISHED, ended.status)
    }

    @Test
    fun `round has trivia only when exactly four options`() {
        val withFour = TestFixtures.roundDto(triviaOptions = listOf("A", "B", "C", "D")).toModel()
        val withThree = TestFixtures.roundDto(triviaOptions = listOf("A", "B", "C")).toModel()

        assertTrue(withFour.hasTrivia)
        assertFalse(withThree.hasTrivia)
    }
}
