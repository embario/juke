package fm.juke.mobile.data.repository

import fm.juke.mobile.data.local.SessionStore
import fm.juke.mobile.data.network.JukeApiService
import fm.juke.mobile.model.Album
import fm.juke.mobile.model.Artist
import fm.juke.mobile.model.FeaturedGenre
import fm.juke.mobile.model.Track
import fm.juke.mobile.model.toDomain

class CatalogRepository(
    private val api: JukeApiService,
    private val store: SessionStore,
) {
    suspend fun searchArtists(query: String): Result<List<Artist>> = runCatching {
        val session = store.current() ?: error("Not authenticated")
        api.searchArtists("Token ${session.token}", query)
            .results
            .map { it.toDomain() }
    }

    suspend fun searchAlbums(query: String): Result<List<Album>> = runCatching {
        val session = store.current() ?: error("Not authenticated")
        api.searchAlbums("Token ${session.token}", query)
            .results
            .map { it.toDomain() }
    }

    suspend fun searchTracks(query: String): Result<List<Track>> = runCatching {
        val session = store.current() ?: error("Not authenticated")
        api.searchTracks("Token ${session.token}", query)
            .results
            .map { it.toDomain() }
    }

    suspend fun featuredGenres(): Result<List<FeaturedGenre>> = runCatching {
        val session = store.current() ?: error("Not authenticated")
        api.featuredGenres("Token ${session.token}")
            .map { it.toDomain() }
    }
}
