package fm.juke.mobile.model

import fm.juke.mobile.data.network.dto.AlbumDto
import fm.juke.mobile.data.network.dto.ArtistDto
import fm.juke.mobile.data.network.dto.FeaturedGenreDto
import fm.juke.mobile.data.network.dto.TrackDto
import fm.juke.mobile.data.network.dto.FeaturedArtistDto

enum class CatalogResourceType(val label: String) {
    ARTISTS("Artists"),
    ALBUMS("Albums"),
    TRACKS("Tracks"),
}

data class Artist(
    val id: Int,
    val name: String,
    val imageUrl: String,
    val followers: Int,
    val popularity: Int,
    val spotifyUri: String,
)

data class Album(
    val id: Int,
    val name: String,
    val albumType: String,
    val releaseDate: String,
    val totalTracks: Int,
    val imageUrl: String,
    val spotifyUri: String,
)

data class Track(
    val id: Int,
    val name: String,
    val durationMs: Int,
    val trackNumber: Int,
    val explicit: Boolean,
    val spotifyUri: String,
)

data class FeaturedArtist(
    val id: String,
    val name: String,
    val imageUrl: String,
)

data class FeaturedGenre(
    val id: String,
    val name: String,
    val spotifyId: String,
    val topArtists: List<FeaturedArtist>,
)

fun ArtistDto.toDomain(): Artist = Artist(
    id = id ?: hashCode(),
    name = name.orEmpty(),
    imageUrl = spotifyData?.images?.firstOrNull().orEmpty(),
    followers = spotifyData?.followers ?: 0,
    popularity = spotifyData?.popularity ?: 0,
    spotifyUri = spotifyData?.uri.orEmpty(),
)

fun AlbumDto.toDomain(): Album = Album(
    id = id ?: hashCode(),
    name = name.orEmpty(),
    albumType = albumType.orEmpty().ifBlank { "ALBUM" },
    releaseDate = releaseDate.orEmpty(),
    totalTracks = totalTracks ?: 0,
    imageUrl = spotifyData?.images?.firstOrNull().orEmpty(),
    spotifyUri = spotifyData?.uri.orEmpty(),
)

fun TrackDto.toDomain(): Track = Track(
    id = id ?: hashCode(),
    name = name.orEmpty(),
    durationMs = durationMs ?: 0,
    trackNumber = trackNumber ?: 0,
    explicit = explicit ?: false,
    spotifyUri = spotifyData?.uri.orEmpty(),
)

fun FeaturedArtistDto.toDomain(): FeaturedArtist = FeaturedArtist(
    id = id.orEmpty(),
    name = name.orEmpty(),
    imageUrl = imageUrl.orEmpty(),
)

fun FeaturedGenreDto.toDomain(): FeaturedGenre = FeaturedGenre(
    id = id.orEmpty(),
    name = name.orEmpty(),
    spotifyId = spotifyId.orEmpty(),
    topArtists = topArtists.map { it.toDomain() },
)
