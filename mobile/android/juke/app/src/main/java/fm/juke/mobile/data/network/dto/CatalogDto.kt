package fm.juke.mobile.data.network.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class SpotifyDataDto(
    val images: List<String>? = null,
    val followers: Int? = null,
    val popularity: Int? = null,
    val uri: String? = null,
)

@Serializable
data class ArtistDto(
    val id: Int? = null,
    val pk: Int? = null,
    val name: String? = null,
    @SerialName("spotify_id") val spotifyId: String? = null,
    @SerialName("spotify_data") val spotifyData: SpotifyDataDto? = null,
)

@Serializable
data class AlbumDto(
    val id: Int? = null,
    val name: String? = null,
    @SerialName("album_type") val albumType: String? = null,
    @SerialName("release_date") val releaseDate: String? = null,
    @SerialName("total_tracks") val totalTracks: Int? = null,
    @SerialName("spotify_data") val spotifyData: SpotifyDataDto? = null,
)

@Serializable
data class TrackDto(
    val id: Int? = null,
    val name: String? = null,
    @SerialName("duration_ms") val durationMs: Int? = null,
    @SerialName("track_number") val trackNumber: Int? = null,
    val explicit: Boolean? = null,
    @SerialName("spotify_data") val spotifyData: SpotifyDataDto? = null,
)

@Serializable
data class FeaturedArtistDto(
    val id: String? = null,
    val name: String? = null,
    @SerialName("image_url") val imageUrl: String? = null,
)

@Serializable
data class FeaturedGenreDto(
    val id: String? = null,
    val name: String? = null,
    @SerialName("spotify_id") val spotifyId: String? = null,
    @SerialName("top_artists") val topArtists: List<FeaturedArtistDto> = emptyList(),
)

@Serializable
data class PaginatedArtists(
    val results: List<ArtistDto> = emptyList(),
)

@Serializable
data class PaginatedAlbums(
    val results: List<AlbumDto> = emptyList(),
)

@Serializable
data class PaginatedTracks(
    val results: List<TrackDto> = emptyList(),
)
