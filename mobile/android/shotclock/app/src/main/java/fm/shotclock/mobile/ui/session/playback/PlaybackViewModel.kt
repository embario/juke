package fm.shotclock.mobile.ui.session.playback

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

data class PlaybackUiState(
    val isLoading: Boolean = true,
    val session: PowerHourSession? = null,
    val players: List<SessionPlayer> = emptyList(),
    val tracks: List<SessionTrack> = emptyList(),
    val secondsRemaining: Int = 0,
    val error: String? = null,
    val isPausing: Boolean = false,
    val isSkipping: Boolean = false,
    val isEnding: Boolean = false,
    val hasEnded: Boolean = false,
)

class PlaybackViewModel(
    private val sessionId: String,
    private val currentUsername: String,
    private val repository: PowerHourRepository = ServiceLocator.powerHourRepository,
) : ViewModel() {

    var uiState by mutableStateOf(PlaybackUiState())
        private set

    private var pollingJob: Job? = null
    private var countdownJob: Job? = null

    val isAdmin: Boolean
        get() = uiState.players.any { it.username == currentUsername && it.isAdmin }

    val currentTrack: SessionTrack?
        get() {
            val session = uiState.session ?: return null
            val index = session.currentTrackIndex
            return if (index in uiState.tracks.indices) uiState.tracks[index] else null
        }

    val trackProgress: String
        get() {
            val session = uiState.session ?: return ""
            val current = session.currentTrackIndex + 1
            val total = uiState.tracks.size
            return "Track $current of $total"
        }

    init {
        loadSession()
    }

    fun loadSession() {
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            repository.getSession(sessionId)
                .onSuccess { session ->
                    uiState = uiState.copy(
                        isLoading = false,
                        session = session,
                        hasEnded = session.status == SessionStatus.ENDED,
                    )
                    loadPlayers()
                    loadTracks()
                    if (session.status == SessionStatus.ACTIVE) {
                        startCountdown(session.secondsPerTrack)
                    }
                    startPolling()
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(
                        isLoading = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    private fun loadTracks() {
        viewModelScope.launch {
            repository.listTracks(sessionId)
                .onSuccess { tracks ->
                    uiState = uiState.copy(tracks = tracks)
                }
        }
    }

    private fun loadPlayers() {
        viewModelScope.launch {
            repository.listPlayers(sessionId)
                .onSuccess { players ->
                    uiState = uiState.copy(players = players)
                }
        }
    }

    private fun startPolling() {
        pollingJob?.cancel()
        pollingJob = viewModelScope.launch {
            while (isActive) {
                delay(3_000)
                repository.getSession(sessionId)
                    .onSuccess { updated ->
                        val previousIndex = uiState.session?.currentTrackIndex ?: -1
                        val previousStatus = uiState.session?.status
                        uiState = uiState.copy(
                            session = updated,
                            hasEnded = updated.status == SessionStatus.ENDED,
                        )
                        loadPlayers()
                        loadTracks()
                        // Reset countdown on track change or resume
                        if (updated.currentTrackIndex != previousIndex ||
                            (previousStatus == SessionStatus.PAUSED && updated.status == SessionStatus.ACTIVE)
                        ) {
                            startCountdown(updated.secondsPerTrack)
                        }
                        if (updated.status == SessionStatus.PAUSED) {
                            countdownJob?.cancel()
                        }
                        if (updated.status == SessionStatus.ENDED) {
                            countdownJob?.cancel()
                            pollingJob?.cancel()
                            loadTracks()
                        }
                    }
            }
        }
    }

    private fun startCountdown(seconds: Int) {
        countdownJob?.cancel()
        uiState = uiState.copy(secondsRemaining = seconds)
        countdownJob = viewModelScope.launch {
            var remaining = seconds
            while (isActive && remaining > 0) {
                delay(1_000)
                remaining--
                uiState = uiState.copy(secondsRemaining = remaining)
            }
        }
    }

    fun pauseOrResume() {
        val session = uiState.session ?: return
        viewModelScope.launch {
            uiState = uiState.copy(isPausing = true, error = null)
            val result = when (session.status) {
                SessionStatus.ACTIVE -> repository.pauseSession(sessionId)
                SessionStatus.PAUSED -> repository.resumeSession(sessionId)
                else -> return@launch
            }
            result
                .onSuccess { updated ->
                    uiState = uiState.copy(isPausing = false, session = updated)
                    if (updated.status == SessionStatus.ACTIVE) {
                        startCountdown(updated.secondsPerTrack)
                    } else {
                        countdownJob?.cancel()
                    }
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(
                        isPausing = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    fun skipTrack() {
        viewModelScope.launch {
            uiState = uiState.copy(isSkipping = true, error = null)
            repository.nextTrack(sessionId)
                .onSuccess { updated ->
                    uiState = uiState.copy(
                        isSkipping = false,
                        session = updated,
                        hasEnded = updated.status == SessionStatus.ENDED,
                    )
                    if (updated.status == SessionStatus.ACTIVE) {
                        startCountdown(updated.secondsPerTrack)
                    }
                    if (updated.status == SessionStatus.ENDED) {
                        countdownJob?.cancel()
                        pollingJob?.cancel()
                        loadTracks()
                    }
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(
                        isSkipping = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    fun endSession() {
        viewModelScope.launch {
            uiState = uiState.copy(isEnding = true, error = null)
            repository.endSession(sessionId)
                .onSuccess { updated ->
                    uiState = uiState.copy(
                        isEnding = false,
                        session = updated,
                        hasEnded = true,
                    )
                    countdownJob?.cancel()
                    pollingJob?.cancel()
                    loadTracks()
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(
                        isEnding = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    override fun onCleared() {
        super.onCleared()
        pollingJob?.cancel()
        countdownJob?.cancel()
    }
}
