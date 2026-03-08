package com.juke.shotclock.data.repository

import fm.juke.core.profile.MusicProfile as CoreMusicProfile
import fm.juke.core.profile.ProfileRepository as CoreProfileRepository
import fm.juke.core.session.SessionStore
import com.juke.shotclock.data.network.ShotClockApiService
import com.juke.shotclock.model.MusicProfile
import kotlinx.serialization.json.JsonObject

class ProfileRepository(
    api: ShotClockApiService,
    store: SessionStore,
) {
    private val delegate = CoreProfileRepository(api, store)

    suspend fun fetchMyProfile(): Result<MusicProfile> =
        delegate.fetchMyProfile().map(CoreMusicProfile::toShotClockProfile)

    suspend fun patchProfile(body: JsonObject): Result<Unit> = delegate.patchProfile(body)
}

private fun CoreMusicProfile.toShotClockProfile(): MusicProfile = MusicProfile(
    username = username,
    displayName = displayName,
    name = name,
    tagline = tagline,
    bio = bio,
    location = location,
    avatarUrl = avatarUrl,
    favoriteGenres = favoriteGenres,
    favoriteArtists = favoriteArtists,
    favoriteAlbums = favoriteAlbums,
    favoriteTracks = favoriteTracks,
    isOwner = isOwner,
)
