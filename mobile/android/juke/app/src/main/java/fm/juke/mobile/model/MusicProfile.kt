package fm.juke.mobile.model

import fm.juke.mobile.data.network.dto.MusicProfileDto
import fm.juke.mobile.data.network.dto.ProfileSearchEntry

data class MusicProfile(
    val username: String,
    val displayName: String,
    val name: String,
    val tagline: String,
    val bio: String,
    val location: String,
    val avatarUrl: String,
    val favoriteGenres: List<String>,
    val favoriteArtists: List<String>,
    val favoriteAlbums: List<String>,
    val favoriteTracks: List<String>,
    val onboardingCompletedAt: String?,
    val isOwner: Boolean,
)

data class ProfileSummary(
    val username: String,
    val displayName: String,
    val tagline: String,
    val avatarUrl: String,
)

fun MusicProfileDto.toDomain(): MusicProfile = MusicProfile(
    username = username.orEmpty(),
    displayName = displayName.orEmpty().ifBlank { username.orEmpty() },
    name = name.orEmpty(),
    tagline = tagline.orEmpty(),
    bio = bio.orEmpty(),
    location = location.orEmpty(),
    avatarUrl = avatarUrl.orEmpty(),
    favoriteGenres = favoriteGenres,
    favoriteArtists = favoriteArtists,
    favoriteAlbums = favoriteAlbums,
    favoriteTracks = favoriteTracks,
    onboardingCompletedAt = onboardingCompletedAt,
    isOwner = isOwner ?: false,
)

fun ProfileSearchEntry.toSummary(): ProfileSummary = ProfileSummary(
    username = username,
    displayName = displayName.orEmpty().ifBlank { username },
    tagline = tagline.orEmpty(),
    avatarUrl = avatarUrl.orEmpty(),
)
