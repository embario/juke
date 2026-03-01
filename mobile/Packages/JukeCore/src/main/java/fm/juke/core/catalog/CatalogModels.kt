package fm.juke.core.catalog

import fm.juke.core.catalog.dto.ArtistDto
import fm.juke.core.catalog.dto.AlbumDto
import fm.juke.core.catalog.dto.TrackDto
import fm.juke.core.catalog.dto.FeaturedArtistDto
import fm.juke.core.catalog.dto.FeaturedGenreDto

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
    val spotifyId: String = "",
    val previewUrl: String = "",
    val albumName: String = "",
    val artistName: String = "",
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
    spotifyId = spotifyData?.spotifyId.orEmpty(),
    previewUrl = spotifyData?.previewUrl.orEmpty(),
    albumName = album?.name.orEmpty(),
    artistName = album?.artists?.firstOrNull()?.name.orEmpty(),
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
