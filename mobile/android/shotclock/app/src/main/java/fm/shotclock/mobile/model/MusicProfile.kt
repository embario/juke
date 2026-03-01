package fm.shotclock.mobile.model

import fm.juke.core.profile.dto.MusicProfileDto

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
    val isOwner: Boolean,
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
    isOwner = isOwner ?: false,
)
