package fm.shotclock.mobile.ui.session.create

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.shotclock.mobile.core.di.ServiceLocator
import fm.shotclock.mobile.data.network.dto.CreateSessionRequest
import fm.juke.core.network.humanReadableMessage
import fm.shotclock.mobile.data.repository.PowerHourRepository
import fm.shotclock.mobile.model.PowerHourSession
import kotlinx.coroutines.launch

data class CreateSessionUiState(
    val title: String = "",
    val tracksPerPlayer: Int = 3,
    val maxTracks: Int = 30,
    val secondsPerTrack: Int = 60,
    val transitionClip: String = "airhorn",
    val hideTrackOwners: Boolean = false,
    val isLoading: Boolean = false,
    val error: String? = null,
)

class CreateSessionViewModel(
    private val repository: PowerHourRepository = ServiceLocator.powerHourRepository,
) : ViewModel() {

    var uiState by mutableStateOf(CreateSessionUiState())
        private set

    fun updateTitle(value: String) {
        uiState = uiState.copy(title = value, error = null)
    }

    fun updateTracksPerPlayer(value: Int) {
        uiState = uiState.copy(tracksPerPlayer = value.coerceIn(1, 10))
    }

    fun updateMaxTracks(value: Int) {
        val snapped = (value / 5) * 5
        uiState = uiState.copy(maxTracks = snapped.coerceIn(10, 60))
    }

    fun updateSecondsPerTrack(value: Int) {
        val snapped = (value / 10) * 10
        uiState = uiState.copy(secondsPerTrack = snapped.coerceIn(30, 120))
    }

    fun updateTransitionClip(value: String) {
        uiState = uiState.copy(transitionClip = value)
    }

    fun toggleHideTrackOwners() {
        uiState = uiState.copy(hideTrackOwners = !uiState.hideTrackOwners)
    }

    fun createSession(onSuccess: (PowerHourSession) -> Unit) {
        val title = uiState.title.trim()
        if (title.isBlank()) {
            uiState = uiState.copy(error = "Session title is required.")
            return
        }
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            val request = CreateSessionRequest(
                title = title,
                tracksPerPlayer = uiState.tracksPerPlayer,
                maxTracks = uiState.maxTracks,
                secondsPerTrack = uiState.secondsPerTrack,
                transitionClip = uiState.transitionClip,
                hideTrackOwners = uiState.hideTrackOwners,
            )
            repository.createSession(request)
                .onSuccess { session ->
                    uiState = uiState.copy(isLoading = false)
                    onSuccess(session)
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(
                        isLoading = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }
}
