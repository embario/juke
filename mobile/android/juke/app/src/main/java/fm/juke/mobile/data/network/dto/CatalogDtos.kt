package fm.juke.mobile.data.network.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class ArtistSearchResponse(
    val href: String? = null,
    val results: List<ArtistDto> = emptyList(),
    val limit: Int? = null,
    val count: Int? = null,
    val offset: Int? = null,
)

@Serializable
data class AlbumSearchResponse(
    val href: String? = null,
    val results: List<AlbumDto> = emptyList(),
    val limit: Int? = null,
    val count: Int? = null,
    val offset: Int? = null,
)

@Serializable
data class TrackSearchResponse(
    val href: String? = null,
    val results: List<TrackDto> = emptyList(),
    val limit: Int? = null,
    val count: Int? = null,
    val offset: Int? = null,
)

@Serializable
data class ArtistDto(
    val id: Int? = null,
    val url: String? = null,
    val name: String? = null,
    @SerialName("spotify_id") val spotifyId: String? = null,
    @SerialName("spotify_data") val spotifyData: SpotifyArtistData? = null,
)

@Serializable
data class SpotifyArtistData(
    val uri: String? = null,
    val popularity: Int? = null,
    val followers: Int? = null,
    val images: List<String> = emptyList(),
)

@Serializable
data class AlbumDto(
    val id: Int? = null,
    val url: String? = null,
    val name: String? = null,
    @SerialName("spotify_id") val spotifyId: String? = null,
    @SerialName("total_tracks") val totalTracks: Int? = null,
    @SerialName("release_date") val releaseDate: String? = null,
    @SerialName("album_type") val albumType: String? = null,
    val artists: List<String> = emptyList(),
    @SerialName("spotify_data") val spotifyData: SpotifyAlbumData? = null,
)

@Serializable
data class SpotifyAlbumData(
    val uri: String? = null,
    val images: List<String> = emptyList(),
)

@Serializable
data class TrackDto(
    val id: Int? = null,
    val url: String? = null,
    val name: String? = null,
    @SerialName("spotify_id") val spotifyId: String? = null,
    @SerialName("duration_ms") val durationMs: Int? = null,
    @SerialName("track_number") val trackNumber: Int? = null,
    @SerialName("disc_number") val discNumber: Int? = null,
    val explicit: Boolean? = null,
    @SerialName("album_link") val albumLink: String? = null,
    @SerialName("spotify_data") val spotifyData: SpotifyTrackData? = null,
)

@Serializable
data class SpotifyTrackData(
    val uri: String? = null,
    val id: String? = null,
    val type: String? = null,
)
