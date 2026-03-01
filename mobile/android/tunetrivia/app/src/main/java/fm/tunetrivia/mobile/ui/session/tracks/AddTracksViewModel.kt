package fm.tunetrivia.mobile.ui.session.tracks

import androidx.compose.runtime.State
import androidx.compose.runtime.mutableStateOf
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.juke.core.network.humanReadableMessage
import fm.tunetrivia.mobile.core.di.ServiceLocator
import fm.tunetrivia.mobile.data.repository.TuneTriviaRepository
import fm.tunetrivia.mobile.model.SpotifyTrack
import kotlinx.coroutines.launch

data class AddTracksUiState(
    val query: String = "",
    val results: List<SpotifyTrack> = emptyList(),
    val isSearching: Boolean = false,
    val isAutoSelecting: Boolean = false,
    val isAddingTrack: Boolean = false,
    val addingTrackId: String? = null,
    val error: String? = null,
    val success: String? = null,
)

class AddTracksViewModel(
    private val repository: TuneTriviaRepository = ServiceLocator.tuneTriviaRepository,
) : ViewModel() {
    private val _uiState = mutableStateOf(AddTracksUiState())
    val uiState: State<AddTracksUiState> = _uiState

    fun updateQuery(value: String) {
        _uiState.value = _uiState.value.copy(query = value, error = null, success = null)
    }

    fun search() {
        if (_uiState.value.isAddingTrack || _uiState.value.isAutoSelecting) return
        val query = _uiState.value.query.trim()
        if (query.isBlank()) return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isSearching = true, error = null, success = null)
            repository.searchTracks(query)
                .onSuccess { tracks ->
                    _uiState.value = _uiState.value.copy(isSearching = false, results = tracks)
                }
                .onFailure { throwable ->
                    _uiState.value = _uiState.value.copy(
                        isSearching = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    fun addTrack(sessionId: Int, track: SpotifyTrack) {
        if (_uiState.value.isAddingTrack || _uiState.value.isAutoSelecting) return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isAddingTrack = true,
                addingTrackId = track.id,
                error = null,
                success = null,
            )
            repository.addTrack(sessionId, track.id)
                .onSuccess {
                    _uiState.value = _uiState.value.copy(
                        isAddingTrack = false,
                        addingTrackId = null,
                        success = "Added \"${track.name}\"",
                        results = _uiState.value.results.filterNot { it.id == track.id },
                    )
                }
                .onFailure { throwable ->
                    _uiState.value = _uiState.value.copy(
                        isAddingTrack = false,
                        addingTrackId = null,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    fun autoFill(sessionId: Int, count: Int, onDone: () -> Unit) {
        if (_uiState.value.isAddingTrack || _uiState.value.isAutoSelecting) return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isAutoSelecting = true,
                error = null,
                success = null,
            )
            repository.autoSelectTracks(sessionId, count)
                .onSuccess { rounds ->
                    _uiState.value = _uiState.value.copy(
                        isAutoSelecting = false,
                        success = "Added ${rounds.size} tracks",
                    )
                    onDone()
                }
                .onFailure { throwable ->
                    _uiState.value = _uiState.value.copy(
                        isAutoSelecting = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }
}
