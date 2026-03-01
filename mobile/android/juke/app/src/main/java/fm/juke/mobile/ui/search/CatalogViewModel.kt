package fm.juke.mobile.ui.search

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.juke.mobile.core.di.ServiceLocator
import fm.juke.core.catalog.Album
import fm.juke.core.catalog.Artist
import fm.juke.core.catalog.CatalogRepository
import fm.juke.core.catalog.CatalogResourceType
import fm.juke.core.catalog.Track
import fm.juke.core.network.humanReadableMessage
import kotlinx.coroutines.launch

data class CatalogUiState(
    val query: String = "",
    val activeTab: CatalogResourceType = CatalogResourceType.ARTISTS,
    val isLoading: Boolean = false,
    val artists: List<Artist> = emptyList(),
    val albums: List<Album> = emptyList(),
    val tracks: List<Track> = emptyList(),
    val error: String? = null,
)

class CatalogViewModel(
    private val repository: CatalogRepository = ServiceLocator.catalogRepository,
) : ViewModel() {

    var uiState by mutableStateOf(CatalogUiState())
        private set

    fun updateQuery(value: String) {
        uiState = uiState.copy(query = value, error = null)
    }

    fun setTab(tab: CatalogResourceType) {
        if (uiState.activeTab == tab) return
        uiState = uiState.copy(activeTab = tab, error = null)
    }

    fun search() {
        val query = uiState.query.trim()
        if (query.length < 2) {
            uiState = uiState.copy(error = "Enter at least two characters.")
            return
        }
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            when (uiState.activeTab) {
                CatalogResourceType.ARTISTS -> {
                    repository.searchArtists(query)
                        .onSuccess { artists ->
                            uiState = uiState.copy(isLoading = false, artists = artists)
                        }
                        .onFailure { throwable ->
                            uiState = uiState.copy(isLoading = false, error = throwable.humanReadableMessage())
                        }
                }
                CatalogResourceType.ALBUMS -> {
                    repository.searchAlbums(query)
                        .onSuccess { albums ->
                            uiState = uiState.copy(isLoading = false, albums = albums)
                        }
                        .onFailure { throwable ->
                            uiState = uiState.copy(isLoading = false, error = throwable.humanReadableMessage())
                        }
                }
                CatalogResourceType.TRACKS -> {
                    repository.searchTracks(query)
                        .onSuccess { tracks ->
                            uiState = uiState.copy(isLoading = false, tracks = tracks)
                        }
                        .onFailure { throwable ->
                            uiState = uiState.copy(isLoading = false, error = throwable.humanReadableMessage())
                        }
                }
            }
        }
    }
}
