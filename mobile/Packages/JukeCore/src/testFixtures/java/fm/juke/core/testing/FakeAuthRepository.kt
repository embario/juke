package fm.juke.core.testing

import fm.juke.core.auth.AuthRepositoryContract
import fm.juke.core.session.SessionSnapshot
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow

class FakeAuthRepository : AuthRepositoryContract {
    private val sessionFlow = MutableStateFlow<SessionSnapshot?>(null)

    var loginResult: Result<Unit> = Result.success(Unit)
    var registerResult: Result<String> = Result.success("ok")
    var logoutCalls: Int = 0

    override val session: Flow<SessionSnapshot?> = sessionFlow

    override suspend fun login(username: String, password: String): Result<Unit> = loginResult

    override suspend fun register(
        username: String,
        email: String,
        password: String,
        confirm: String,
    ): Result<String> = registerResult

    override suspend fun logout() {
        logoutCalls += 1
        sessionFlow.value = null
    }

    override suspend fun currentSession(): SessionSnapshot? = sessionFlow.value

    fun setSession(snapshot: SessionSnapshot?) {
        sessionFlow.value = snapshot
    }
}
