package fm.tunetrivia.mobile.ui.session.lobby

import androidx.compose.runtime.State
import androidx.compose.runtime.mutableStateOf
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.juke.core.network.humanReadableMessage
import fm.tunetrivia.mobile.core.di.ServiceLocator
import fm.tunetrivia.mobile.data.repository.TuneTriviaRepository
import fm.tunetrivia.mobile.model.SessionDetail
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

data class LobbyUiState(
    val isLoading: Boolean = true,
    val session: SessionDetail? = null,
    val error: String? = null,
    val isStarting: Boolean = false,
)

class SessionLobbyViewModel(
    private val repository: TuneTriviaRepository = ServiceLocator.tuneTriviaRepository,
) : ViewModel() {
    private val _uiState = mutableStateOf(LobbyUiState())
    val uiState: State<LobbyUiState> = _uiState

    private var pollJob: Job? = null

    fun load(sessionId: Int) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            repository.getSession(sessionId)
                .onSuccess { detail ->
                    _uiState.value = LobbyUiState(isLoading = false, session = detail)
                }
                .onFailure { throwable ->
                    _uiState.value = LobbyUiState(
                        isLoading = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    fun startPolling(sessionId: Int) {
        if (pollJob != null) return
        pollJob = viewModelScope.launch {
            while (true) {
                repository.getSession(sessionId)
                    .onSuccess { detail ->
                        _uiState.value = _uiState.value.copy(session = detail, error = null)
                    }
                delay(3000)
            }
        }
    }

    fun stopPolling() {
        pollJob?.cancel()
        pollJob = null
    }

    fun startGame(sessionId: Int, onStarted: () -> Unit) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isStarting = true)
            repository.startGame(sessionId)
                .onSuccess {
                    _uiState.value = _uiState.value.copy(isStarting = false)
                    onStarted()
                }
                .onFailure { throwable ->
                    _uiState.value = _uiState.value.copy(
                        isStarting = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    fun addPlayer(sessionId: Int, name: String, onComplete: () -> Unit) {
        if (name.isBlank()) return
        viewModelScope.launch {
            repository.addManualPlayer(sessionId, name)
                .onSuccess {
                    onComplete()
                    load(sessionId)
                }
        }
    }
}
