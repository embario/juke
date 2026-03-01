package fm.shotclock.mobile.data.network.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class SessionDto(
    val id: String,
    val title: String,
    @SerialName("invite_code") val inviteCode: String,
    val status: String,
    @SerialName("tracks_per_player") val tracksPerPlayer: Int,
    @SerialName("max_tracks") val maxTracks: Int,
    @SerialName("seconds_per_track") val secondsPerTrack: Int,
    @SerialName("transition_clip") val transitionClip: String,
    @SerialName("hide_track_owners") val hideTrackOwners: Boolean,
    @SerialName("current_track_index") val currentTrackIndex: Int,
    val admin: Int? = null,
    @SerialName("player_count") val playerCount: Int = 0,
    @SerialName("track_count") val trackCount: Int = 0,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("started_at") val startedAt: String? = null,
    @SerialName("ended_at") val endedAt: String? = null,
)

@Serializable
data class SessionPlayerDto(
    val id: String,
    val user: SessionPlayerUserDto,
    @SerialName("is_admin") val isAdmin: Boolean,
)

@Serializable
data class SessionPlayerUserDto(
    val id: Int,
    val username: String,
    @SerialName("display_name") val displayName: String? = null,
)

@Serializable
data class SessionTrackDto(
    val id: String,
    @SerialName("track_id") val trackId: Int,
    val order: Int,
    @SerialName("start_offset_ms") val startOffsetMs: Int = 0,
    @SerialName("track_name") val trackName: String? = null,
    @SerialName("track_artist") val trackArtist: String? = null,
    @SerialName("track_album") val trackAlbum: String? = null,
    @SerialName("duration_ms") val durationMs: Int? = null,
    @SerialName("spotify_id") val spotifyId: String? = null,
    @SerialName("preview_url") val previewUrl: String? = null,
    @SerialName("added_by_username") val addedByUsername: String? = null,
)

@Serializable
data class SessionStateDto(
    val status: String,
    @SerialName("current_track_index") val currentTrackIndex: Int,
    @SerialName("started_at") val startedAt: String? = null,
    @SerialName("player_count") val playerCount: Int = 0,
    @SerialName("track_count") val trackCount: Int = 0,
)

@Serializable
data class CreateSessionRequest(
    val title: String,
    @SerialName("tracks_per_player") val tracksPerPlayer: Int,
    @SerialName("max_tracks") val maxTracks: Int,
    @SerialName("seconds_per_track") val secondsPerTrack: Int,
    @SerialName("transition_clip") val transitionClip: String,
    @SerialName("hide_track_owners") val hideTrackOwners: Boolean,
)

@Serializable
data class JoinSessionRequest(
    @SerialName("invite_code") val inviteCode: String,
)

@Serializable
data class AddTrackRequest(
    @SerialName("track_id") val trackId: Int,
    @SerialName("start_offset_ms") val startOffsetMs: Int = 0,
)

@Serializable
data class ImportSessionTracksRequest(
    @SerialName("source_session_id") val sourceSessionId: String,
)

@Serializable
data class ImportSessionTracksResponse(
    val imported: Int = 0,
)
