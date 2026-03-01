package fm.juke.core.auth

import fm.juke.core.auth.dto.LoginRequest
import fm.juke.core.auth.dto.RegisterRequest
import fm.juke.core.network.CoreApiService
import fm.juke.core.session.SessionSnapshot
import fm.juke.core.session.SessionStore
import kotlinx.coroutines.flow.Flow

class AuthRepository(
    private val api: CoreApiService,
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
        response.detail ?: "Check your inbox to confirm your account."
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
