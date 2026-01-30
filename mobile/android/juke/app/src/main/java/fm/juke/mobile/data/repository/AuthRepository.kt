package fm.juke.mobile.data.repository

import fm.juke.mobile.data.local.SessionSnapshot
import fm.juke.mobile.data.local.SessionStore
import fm.juke.mobile.data.network.JukeApiService
import fm.juke.mobile.data.network.dto.LoginRequest
import fm.juke.mobile.data.network.dto.RegisterRequest
import kotlinx.coroutines.flow.Flow

class AuthRepository(
    private val api: JukeApiService,
    private val store: SessionStore,
) : AuthRepositoryContract {

    override val session: Flow<SessionSnapshot?> = store.snapshot

    override suspend fun login(username: String, password: String): Result<Unit> = runCatching {
        val response = api.login(LoginRequest(username, password))
        store.save(SessionSnapshot(username, response.token))
    }

    override suspend fun register(
        username: String,
        email: String,
        password: String,
        confirm: String,
    ): Result<String> = runCatching {
        val response = api.register(RegisterRequest(username, email, password, confirm))
        response.detail ?: "Account created. Please verify your email."
    }

    override suspend fun logout() {
        val snapshot = store.current()
        if (snapshot != null) {
            runCatching { api.logout("Token ${snapshot.token}") }
        }
        store.clear()
    }

    override suspend fun currentSession(): SessionSnapshot? = store.current()
}
