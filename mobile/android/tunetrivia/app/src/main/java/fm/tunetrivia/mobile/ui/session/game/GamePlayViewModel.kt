package fm.tunetrivia.mobile.ui.session.game

import androidx.compose.runtime.State
import androidx.compose.runtime.mutableStateOf
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.tunetrivia.mobile.core.di.ServiceLocator
import fm.tunetrivia.mobile.data.network.humanReadableMessage
import fm.tunetrivia.mobile.data.repository.TuneTriviaRepository
import fm.tunetrivia.mobile.model.SessionDetail
import fm.tunetrivia.mobile.model.TriviaResult
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

data class GameUiState(
    val isLoading: Boolean = true,
    val session: SessionDetail? = null,
    val error: String? = null,
    val isSubmittingGuess: Boolean = false,
    val isSubmittingTrivia: Boolean = false,
    val triviaResult: TriviaResult? = null,
    val isAdvancing: Boolean = false,
    val isEnding: Boolean = false,
)

class GamePlayViewModel(
    private val repository: TuneTriviaRepository = ServiceLocator.tuneTriviaRepository,
) : ViewModel() {
    private val _uiState = mutableStateOf(GameUiState())
    val uiState: State<GameUiState> = _uiState

    private var pollJob: Job? = null

    fun load(sessionId: Int) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            repository.getSession(sessionId)
                .onSuccess { detail ->
                    _uiState.value = GameUiState(isLoading = false, session = detail)
                }
                .onFailure { throwable ->
                    _uiState.value = GameUiState(
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
                delay(2000)
            }
        }
    }

    fun stopPolling() {
        pollJob?.cancel()
        pollJob = null
    }

    fun submitGuess(roundId: Int, song: String?, artist: String?, onSuccess: () -> Unit) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isSubmittingGuess = true, error = null)
            repository.submitGuess(roundId, song, artist)
                .onSuccess {
                    _uiState.value = _uiState.value.copy(isSubmittingGuess = false)
                    onSuccess()
                }
                .onFailure { throwable ->
                    _uiState.value = _uiState.value.copy(
                        isSubmittingGuess = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    fun submitTrivia(roundId: Int, answer: String, onSuccess: () -> Unit) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isSubmittingTrivia = true, error = null)
            repository.submitTrivia(roundId, answer)
                .onSuccess { result ->
                    _uiState.value = _uiState.value.copy(
                        isSubmittingTrivia = false,
                        triviaResult = result,
                    )
                    onSuccess()
                }
                .onFailure { throwable ->
                    _uiState.value = _uiState.value.copy(
                        isSubmittingTrivia = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    fun revealRound(sessionId: Int) {
        viewModelScope.launch {
            repository.revealRound(sessionId)
                .onFailure { throwable ->
                    _uiState.value = _uiState.value.copy(error = throwable.humanReadableMessage())
                }
        }
    }

    fun nextRound(sessionId: Int) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isAdvancing = true)
            repository.nextRound(sessionId)
                .onSuccess {
                    _uiState.value = _uiState.value.copy(isAdvancing = false, triviaResult = null)
                }
                .onFailure { throwable ->
                    _uiState.value = _uiState.value.copy(
                        isAdvancing = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    fun endGame(sessionId: Int) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isEnding = true)
            repository.endGame(sessionId)
                .onSuccess {
                    _uiState.value = _uiState.value.copy(isEnding = false)
                }
                .onFailure { throwable ->
                    _uiState.value = _uiState.value.copy(
                        isEnding = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    fun awardPoints(playerId: Int, points: Int) {
        viewModelScope.launch {
            repository.awardPoints(playerId, points)
        }
    }
}
