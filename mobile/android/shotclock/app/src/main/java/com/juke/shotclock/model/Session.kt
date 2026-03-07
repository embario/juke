package com.juke.shotclock.model

import com.juke.shotclock.data.network.dto.SessionDto

enum class SessionStatus(val label: String) {
    LOBBY("Lobby"),
    ACTIVE("Active"),
    PAUSED("Paused"),
    ENDED("Ended"),
    ;

    companion object {
        fun fromString(value: String): SessionStatus = when (value.lowercase()) {
            "lobby" -> LOBBY
            "active" -> ACTIVE
            "paused" -> PAUSED
            "ended" -> ENDED
            else -> LOBBY
        }
    }
}

data class PowerHourSession(
    val id: String,
    val title: String,
    val inviteCode: String,
    val status: SessionStatus,
    val tracksPerPlayer: Int,
    val maxTracks: Int,
    val secondsPerTrack: Int,
    val transitionClip: String,
    val hideTrackOwners: Boolean,
    val currentTrackIndex: Int,
    val adminId: Int,
    val playerCount: Int,
    val trackCount: Int,
    val createdAt: String?,
    val startedAt: String?,
    val endedAt: String?,
)

fun SessionDto.toDomain(): PowerHourSession = PowerHourSession(
    id = id,
    title = title,
    inviteCode = inviteCode,
    status = SessionStatus.fromString(status),
    tracksPerPlayer = tracksPerPlayer,
    maxTracks = maxTracks,
    secondsPerTrack = secondsPerTrack,
    transitionClip = transitionClip,
    hideTrackOwners = hideTrackOwners,
    currentTrackIndex = currentTrackIndex,
    adminId = admin ?: 0,
    playerCount = playerCount,
    trackCount = trackCount,
    createdAt = createdAt,
    startedAt = startedAt,
    endedAt = endedAt,
)
