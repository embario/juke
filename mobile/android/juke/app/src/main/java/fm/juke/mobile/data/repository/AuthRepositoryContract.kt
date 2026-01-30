package fm.juke.mobile.data.repository

import fm.juke.mobile.data.local.SessionSnapshot
import kotlinx.coroutines.flow.Flow

interface AuthRepositoryContract {
    val session: Flow<SessionSnapshot?>

    suspend fun login(username: String, password: String): Result<Unit>

    suspend fun register(
        username: String,
        email: String,
        password: String,
        confirm: String,
    ): Result<String>

    suspend fun logout()

    suspend fun currentSession(): SessionSnapshot?
}
