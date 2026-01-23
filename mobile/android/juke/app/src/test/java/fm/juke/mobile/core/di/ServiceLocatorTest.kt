package fm.juke.mobile.core.di

import fm.juke.mobile.BuildConfig
import org.junit.Assert.assertEquals
import org.junit.Test

class ServiceLocatorTest {
    @Test
    fun normalizedBaseUrlUsesBuildConfigDefault() {
        val expected = "${BuildConfig.BACKEND_URL.trimEnd('/')}/"
        assertEquals(expected, ServiceLocator.normalizedBaseUrl())
    }

    @Test
    fun normalizedBaseUrlTrimsTrailingSlash() {
        val normalized = ServiceLocator.normalizedBaseUrl("http://example.com///")
        assertEquals("http://example.com/", normalized)
    }
}
