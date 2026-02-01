package fm.juke.mobile.data.network

import java.io.IOException
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import retrofit2.HttpException

private val errorJson = Json { ignoreUnknownKeys = true }

fun Throwable.humanReadableMessage(): String = when (this) {
    is HttpException -> {
        val payload = response()?.errorBody()?.string()
        if (payload.isNullOrBlank()) {
            message ?: "Request failed."
        } else {
            runCatching {
                errorJson.decodeFromString(ErrorEnvelope.serializer(), payload)
            }.getOrNull()?.bestMessage() ?: message ?: "Request failed."
        }
    }

    is IOException -> "We couldn't talk to the Juke servers. Please check your connection."
    else -> localizedMessage ?: "Something unexpected happened."
}

@Serializable
private data class ErrorEnvelope(
    val detail: String? = null,
    val nonFieldErrors: List<String>? = null,
    @SerialName("password_confirm") val passwordConfirm: List<String>? = null,
) {
    fun bestMessage(): String? = detail ?: nonFieldErrors?.firstOrNull() ?: passwordConfirm?.firstOrNull()
}
