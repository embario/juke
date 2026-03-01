package fm.juke.core.profile

import fm.juke.core.network.CoreApiService
import fm.juke.core.session.SessionStore
import kotlinx.serialization.json.JsonObject

open class ProfileRepository(
    private val api: CoreApiService,
    private val store: SessionStore,
) {
    open suspend fun fetchMyProfile(): Result<MusicProfile> = runCatching {
        val session = store.current() ?: error("Not authenticated")
        api.myProfile("Token ${session.token}").toDomain()
    }

    suspend fun searchProfiles(query: String): Result<List<ProfileSummary>> = runCatching {
        val session = store.current() ?: error("Not authenticated")
        api.searchProfiles("Token ${session.token}", query)
            .results
            .map { it.toSummary() }
    }

    suspend fun fetchProfile(username: String): Result<MusicProfile> = runCatching {
        val session = store.current() ?: error("Not authenticated")
        api.getProfile("Token ${session.token}", username).toDomain()
    }

    suspend fun patchProfile(body: JsonObject): Result<Unit> = runCatching {
        val session = store.current() ?: error("Not authenticated")
        api.patchProfile("Token ${session.token}", body)
    }
}
