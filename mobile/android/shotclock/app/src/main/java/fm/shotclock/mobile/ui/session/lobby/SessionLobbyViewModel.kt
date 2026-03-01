package fm.shotclock.mobile.ui.session.lobby

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.shotclock.mobile.core.di.ServiceLocator
import fm.juke.core.network.humanReadableMessage
import fm.shotclock.mobile.data.repository.PowerHourRepository
import fm.shotclock.mobile.model.PowerHourSession
import fm.shotclock.mobile.model.SessionPlayer
import fm.shotclock.mobile.model.SessionStatus
import fm.shotclock.mobile.model.SessionTrack
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

data class SessionLobbyUiState(
    val isLoading: Boolean = true,
    val session: PowerHourSession? = null,
    val players: List<SessionPlayer> = emptyList(),
    val tracks: List<SessionTrack> = emptyList(),
    val error: String? = null,
    val isStarting: Boolean = false,
    val isDeleting: Boolean = false,
    val showDeleteConfirm: Boolean = false,
)

class SessionLobbyViewModel(
    private val sessionId: String,
    private val currentUsername: String,
    private val repository: PowerHourRepository = ServiceLocator.powerHourRepository,
) : ViewModel() {

    var uiState by mutableStateOf(SessionLobbyUiState())
        private set

    private var pollingJob: Job? = null

    val isAdmin: Boolean
        get() = uiState.players.any { it.username == currentUsername && it.isAdmin }

    init {
        loadSession()
    }

    fun loadSession() {
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            val sessionResult = repository.getSession(sessionId)
            sessionResult
                .onSuccess { session ->
                    uiState = uiState.copy(isLoading = false, session = session)
                    loadPlayersAndTracks()
                    startPollingIfLobby()
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(
                        isLoading = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    private fun loadPlayersAndTracks() {
        viewModelScope.launch {
            repository.listPlayers(sessionId)
                .onSuccess { players ->
                    uiState = uiState.copy(players = players)
                }
            repository.listTracks(sessionId)
                .onSuccess { tracks ->
                    uiState = uiState.copy(tracks = tracks)
                }
        }
    }

    private fun startPollingIfLobby() {
        pollingJob?.cancel()
        val session = uiState.session ?: return
        if (session.status != SessionStatus.LOBBY) return
        pollingJob = viewModelScope.launch {
            while (isActive) {
                delay(5_000)
                repository.getSession(sessionId)
                    .onSuccess { updated ->
                        uiState = uiState.copy(session = updated)
                        if (updated.status != SessionStatus.LOBBY) {
                            pollingJob?.cancel()
                        }
                    }
                repository.listPlayers(sessionId)
                    .onSuccess { players -> uiState = uiState.copy(players = players) }
                repository.listTracks(sessionId)
                    .onSuccess { tracks -> uiState = uiState.copy(tracks = tracks) }
            }
        }
    }

    fun startSession(onStarted: () -> Unit) {
        viewModelScope.launch {
            uiState = uiState.copy(isStarting = true, error = null)
            repository.startSession(sessionId)
                .onSuccess { session ->
                    uiState = uiState.copy(isStarting = false, session = session)
                    pollingJob?.cancel()
                    onStarted()
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(
                        isStarting = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    fun showDeleteConfirmation() {
        uiState = uiState.copy(showDeleteConfirm = true)
    }

    fun dismissDeleteConfirmation() {
        uiState = uiState.copy(showDeleteConfirm = false)
    }

    fun deleteSession(onDeleted: () -> Unit) {
        viewModelScope.launch {
            uiState = uiState.copy(isDeleting = true, showDeleteConfirm = false, error = null)
            repository.deleteSession(sessionId)
                .onSuccess {
                    uiState = uiState.copy(isDeleting = false)
                    pollingJob?.cancel()
                    onDeleted()
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(
                        isDeleting = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    fun refreshTracks() {
        viewModelScope.launch {
            repository.listTracks(sessionId)
                .onSuccess { tracks -> uiState = uiState.copy(tracks = tracks) }
        }
    }

    override fun onCleared() {
        super.onCleared()
        pollingJob?.cancel()
    }
}
