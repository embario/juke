package fm.juke.mobile.data.network

import java.io.IOException
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

class NetworkErrorsTest {
    @Test
    fun humanReadableMessage_prefers_detail_from_http_payload() {
        val error = httpException(400, """{"detail":"Track context is invalid."}""")

        assertEquals("Track context is invalid.", error.humanReadableMessage())
    }

    @Test
    fun humanReadableMessage_uses_connection_copy_for_io_failures() {
        val error = IOException("socket closed")

        assertEquals(
            "We couldn't reach the servers. Please check your connection.",
            error.humanReadableMessage(),
        )
    }

    @Test
    fun humanReadableMessage_falls_back_to_localized_message_for_generic_errors() {
        val error = IllegalStateException("Unexpected state")

        assertEquals("Unexpected state", error.humanReadableMessage())
    }

    private fun httpException(statusCode: Int, body: String): HttpException {
        val responseBody = body.toResponseBody("application/json".toMediaType())
        return HttpException(Response.error<Any>(statusCode, responseBody))
    }
}
