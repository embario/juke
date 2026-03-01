package fm.shotclock.mobile.ui.session.tracks

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.shotclock.mobile.core.di.ServiceLocator
import fm.juke.core.network.humanReadableMessage
import fm.shotclock.mobile.data.repository.CatalogRepository
import fm.shotclock.mobile.data.repository.PowerHourRepository
import fm.shotclock.mobile.model.PowerHourSession
import fm.shotclock.mobile.model.SessionTrack
import fm.shotclock.mobile.model.Track
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

enum class AddTracksTab { SEARCH, IMPORT }

data class AddTracksUiState(
    val activeTab: AddTracksTab = AddTracksTab.SEARCH,
    val query: String = "",
    val isSearching: Boolean = false,
    val searchResults: List<Track> = emptyList(),
    val sessionTrackIds: Set<Int> = emptySet(),
    val sessionTracks: List<SessionTrack> = emptyList(),
    val error: String? = null,
    val isLoadingSessions: Boolean = false,
    val previousSessions: List<PowerHourSession> = emptyList(),
    val isImporting: Boolean = false,
)

class AddTracksViewModel(
    private val sessionId: String,
    private val catalogRepository: CatalogRepository = ServiceLocator.catalogRepository,
    private val powerHourRepository: PowerHourRepository = ServiceLocator.powerHourRepository,
) : ViewModel() {

    var uiState by mutableStateOf(AddTracksUiState())
        private set

    private var searchJob: Job? = null

    init {
        loadSessionTracks()
        loadPreviousSessions()
    }

    private fun loadSessionTracks() {
        viewModelScope.launch {
            powerHourRepository.listTracks(sessionId)
                .onSuccess { tracks ->
                    uiState = uiState.copy(
                        sessionTracks = tracks,
                        sessionTrackIds = tracks.map { it.trackId }.toSet(),
                    )
                }
        }
    }

    private fun loadPreviousSessions() {
        viewModelScope.launch {
            uiState = uiState.copy(isLoadingSessions = true)
            powerHourRepository.listSessions()
                .onSuccess { sessions ->
                    val filtered = sessions.filter { it.id != sessionId && it.trackCount > 0 }
                    uiState = uiState.copy(
                        isLoadingSessions = false,
                        previousSessions = filtered,
                    )
                }
                .onFailure {
                    uiState = uiState.copy(isLoadingSessions = false)
                }
        }
    }

    fun switchTab(tab: AddTracksTab) {
        uiState = uiState.copy(activeTab = tab)
    }

    fun updateQuery(value: String) {
        uiState = uiState.copy(query = value, error = null)
        searchJob?.cancel()
        if (value.trim().length >= 2) {
            searchJob = viewModelScope.launch {
                delay(400) // debounce
                performSearch(value.trim())
            }
        } else {
            uiState = uiState.copy(searchResults = emptyList())
        }
    }

    private suspend fun performSearch(query: String) {
        uiState = uiState.copy(isSearching = true, error = null)
        catalogRepository.searchTracks(query)
            .onSuccess { tracks ->
                uiState = uiState.copy(isSearching = false, searchResults = tracks)
            }
            .onFailure { throwable ->
                uiState = uiState.copy(
                    isSearching = false,
                    error = throwable.humanReadableMessage(),
                )
            }
    }

    fun addTrack(track: Track) {
        if (uiState.sessionTrackIds.contains(track.id)) return
        viewModelScope.launch {
            uiState = uiState.copy(error = null)
            powerHourRepository.addTrack(sessionId, track.id)
                .onSuccess { sessionTrack ->
                    uiState = uiState.copy(
                        sessionTrackIds = uiState.sessionTrackIds + track.id,
                        sessionTracks = uiState.sessionTracks + sessionTrack,
                    )
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(error = throwable.humanReadableMessage())
                }
        }
    }

    fun removeTrack(track: Track) {
        val sessionTrack = uiState.sessionTracks.find { it.trackId == track.id } ?: return
        viewModelScope.launch {
            uiState = uiState.copy(error = null)
            powerHourRepository.removeTrack(sessionId, sessionTrack.id)
                .onSuccess {
                    uiState = uiState.copy(
                        sessionTrackIds = uiState.sessionTrackIds - track.id,
                        sessionTracks = uiState.sessionTracks.filter { it.id != sessionTrack.id },
                    )
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(error = throwable.humanReadableMessage())
                }
        }
    }

    fun importFromSession(sourceSessionId: String) {
        viewModelScope.launch {
            uiState = uiState.copy(isImporting = true, error = null)
            powerHourRepository.importSessionTracks(sessionId, sourceSessionId)
                .onSuccess { importedTracks ->
                    val allTracks = uiState.sessionTracks + importedTracks
                    uiState = uiState.copy(
                        isImporting = false,
                        sessionTracks = allTracks,
                        sessionTrackIds = allTracks.map { it.trackId }.toSet(),
                    )
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(
                        isImporting = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }
}
