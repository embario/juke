package com.juke.shotclock.model

import com.juke.shotclock.data.network.dto.SessionTrackDto

data class SessionTrack(
    val id: String,
    val trackId: Int,
    val trackName: String,
    val trackArtist: String,
    val trackAlbum: String,
    val durationMs: Int,
    val spotifyId: String,
    val previewUrl: String,
    val order: Int,
    val startOffsetMs: Int,
    val addedByUsername: String,
)

fun SessionTrackDto.toDomain(): SessionTrack = SessionTrack(
    id = id,
    trackId = trackId,
    trackName = trackName.orEmpty(),
    trackArtist = trackArtist.orEmpty(),
    trackAlbum = trackAlbum.orEmpty(),
    durationMs = durationMs ?: 0,
    spotifyId = spotifyId.orEmpty(),
    previewUrl = previewUrl.orEmpty(),
    order = order,
    startOffsetMs = startOffsetMs,
    addedByUsername = addedByUsername.orEmpty(),
)
