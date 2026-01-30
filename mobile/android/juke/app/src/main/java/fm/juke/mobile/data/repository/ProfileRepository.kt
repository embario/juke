package fm.juke.mobile.data.repository

import fm.juke.mobile.data.local.SessionStore
import fm.juke.mobile.data.network.JukeApiService
import fm.juke.mobile.model.MusicProfile
import fm.juke.mobile.model.ProfileSummary
import fm.juke.mobile.model.toDomain
import fm.juke.mobile.model.toSummary
import kotlinx.serialization.json.JsonObject

class ProfileRepository(
    private val api: JukeApiService,
    private val store: SessionStore,
) {
    suspend fun fetchMyProfile(): Result<MusicProfile> = runCatching {
        val session = store.current() ?: error("Not authenticated")
        val profile = api.myProfile("Token ${session.token}")
        store.setOnboardingCompletedAt(profile.onboardingCompletedAt)
        profile.toDomain()
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
