package com.juke.juke.data.repository

import com.juke.juke.data.local.JukeSessionStore
import fm.juke.core.network.CoreApiService
import fm.juke.core.profile.MusicProfile
import fm.juke.core.profile.ProfileRepository as CoreProfileRepository
import fm.juke.core.profile.toDomain

class ProfileRepository(
    private val api: CoreApiService,
    private val store: JukeSessionStore,
) : CoreProfileRepository(api, store) {

    override suspend fun fetchMyProfile(): Result<MusicProfile> = runCatching {
        val session = store.current() ?: error("Not authenticated")
        val profile = api.myProfile("Token ${session.token}")
        store.setOnboardingCompletedAt(profile.onboardingCompletedAt)
        profile.toDomain()
    }
}
