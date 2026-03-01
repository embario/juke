package fm.shotclock.mobile.model

import fm.juke.core.catalog.dto.TrackDto

data class Track(
    val id: Int,
    val name: String,
    val durationMs: Int,
    val trackNumber: Int,
    val explicit: Boolean,
    val spotifyUri: String,
    val spotifyId: String,
    val previewUrl: String,
    val albumName: String,
    val artistName: String,
)

fun TrackDto.toDomain(): Track = Track(
    id = id ?: hashCode(),
    name = name.orEmpty(),
    durationMs = durationMs ?: 0,
    trackNumber = trackNumber ?: 0,
    explicit = explicit ?: false,
    spotifyUri = spotifyData?.uri.orEmpty(),
    spotifyId = spotifyData?.spotifyId.orEmpty(),
    previewUrl = spotifyData?.previewUrl.orEmpty(),
    albumName = album?.name.orEmpty(),
    artistName = album?.artists?.firstOrNull()?.name.orEmpty(),
)
