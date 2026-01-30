package fm.juke.mobile.data.network

import retrofit2.HttpException
import java.io.IOException

fun Throwable.humanReadableMessage(): String {
    return if (this is HttpException) {
        val code = response()?.code() ?: 0
        val body = response()?.errorBody()?.string()
        when (code) {
            400 -> body?.extractDetail() ?: "Bad request — check your input."
            401 -> "Authentication failed. Please log in again."
            403 -> "Access denied."
            404 -> "Not found."
            429 -> "Rate limited — try again shortly."
            in 500..599 -> "Server error — try again later."
            else -> body?.extractDetail() ?: "Request failed with status $code."
        }
    } else if (this is IOException) {
        "Network error — check your connection."
    } else {
        message ?: "Something went wrong."
    }
}

private fun String.extractDetail(): String? {
    Regex("\"detail\"\\s*:\\s*\"([^\"]+)\"").find(this)?.let { match ->
        return match.groupValues[1]
    }
    Regex("\"non_field_errors\"\\s*:\\s*\\[\"([^\"]+)\"").find(this)?.let { match ->
        return match.groupValues[1]
    }
    return if (length in 1..200) {
        trim().removePrefix("[").removeSuffix("]").trim('"')
    } else {
        null
    }
}
