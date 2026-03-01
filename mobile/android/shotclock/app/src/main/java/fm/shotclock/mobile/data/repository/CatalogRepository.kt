package fm.shotclock.mobile.data.repository

import fm.juke.core.catalog.CatalogRepository as CoreCatalogRepository
import fm.juke.core.catalog.Track as CoreTrack
import fm.juke.core.session.SessionStore
import fm.shotclock.mobile.data.network.ShotClockApiService
import fm.shotclock.mobile.model.Track

class CatalogRepository(
    api: ShotClockApiService,
    store: SessionStore,
) {
    private val delegate = CoreCatalogRepository(api, store)

    suspend fun searchTracks(query: String): Result<List<Track>> =
        delegate.searchTracks(query).map { tracks ->
            tracks.map(CoreTrack::toShotClockTrack)
        }
}

private fun CoreTrack.toShotClockTrack(): Track = Track(
    id = id,
    name = name,
    durationMs = durationMs,
    trackNumber = trackNumber,
    explicit = explicit,
    spotifyUri = spotifyUri,
    spotifyId = spotifyId,
    previewUrl = previewUrl,
    albumName = albumName,
    artistName = artistName,
)
