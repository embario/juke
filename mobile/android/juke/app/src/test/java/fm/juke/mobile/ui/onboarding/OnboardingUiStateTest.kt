package fm.juke.mobile.ui.onboarding

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OnboardingUiStateTest {
    @Test
    fun defaultsReflectFirstStepProgress() {
        val state = OnboardingUiState()
        val expectedProgress = (1.0 / state.totalSteps) * 100.0

        assertEquals(OnboardingStep.GENRES, state.currentStep)
        assertEquals(expectedProgress, state.progress, 0.001)
        assertFalse(state.canGoBack)
        assertTrue(state.canGoNext)
    }
}
