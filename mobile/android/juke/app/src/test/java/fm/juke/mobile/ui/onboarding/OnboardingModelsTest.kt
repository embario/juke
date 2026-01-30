package fm.juke.mobile.ui.onboarding

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OnboardingModelsTest {
    @Test
    fun searchCitiesIsCaseInsensitiveAndLimited() {
        val results = searchCities("an")
        assertTrue(results.any { it.name == "San Francisco" })
        assertTrue(results.size <= 10)
    }

    @Test
    fun onBoardingStepHasExpectedOrder() {
        val steps = OnboardingStep.values().toList()
        assertEquals(OnboardingStep.GENRES, steps.first())
        assertEquals(OnboardingStep.CONNECT, steps.last())
    }
}
