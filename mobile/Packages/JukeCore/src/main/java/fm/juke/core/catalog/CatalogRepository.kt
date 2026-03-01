package fm.juke.core.catalog

import fm.juke.core.network.CoreApiService
import fm.juke.core.session.SessionStore

open class CatalogRepository(
    private val api: CoreApiService,
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
