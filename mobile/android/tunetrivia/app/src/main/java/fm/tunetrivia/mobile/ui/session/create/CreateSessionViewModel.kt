package fm.tunetrivia.mobile.ui.session.create

import androidx.compose.runtime.State
import androidx.compose.runtime.mutableStateOf
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.tunetrivia.mobile.core.di.ServiceLocator
import fm.tunetrivia.mobile.data.network.humanReadableMessage
import fm.tunetrivia.mobile.data.repository.TuneTriviaRepository
import fm.tunetrivia.mobile.model.SessionMode
import kotlinx.coroutines.launch

data class CreateSessionUiState(
    val name: String = "",
    val mode: SessionMode = SessionMode.HOST,
    val maxSongs: Int = 10,
    val secondsPerSong: Int = 20,
    val enableTrivia: Boolean = true,
    val isLoading: Boolean = false,
    val error: String? = null,
)

class CreateSessionViewModel(
    private val repository: TuneTriviaRepository = ServiceLocator.tuneTriviaRepository,
) : ViewModel() {
    private val _uiState = mutableStateOf(CreateSessionUiState())
    val uiState: State<CreateSessionUiState> = _uiState

    fun updateName(value: String) {
        _uiState.value = _uiState.value.copy(name = value, error = null)
    }

    fun updateMode(mode: SessionMode) {
        _uiState.value = _uiState.value.copy(mode = mode)
    }

    fun updateMaxSongs(value: Int) {
        _uiState.value = _uiState.value.copy(maxSongs = value)
    }

    fun updateSecondsPerSong(value: Int) {
        _uiState.value = _uiState.value.copy(secondsPerSong = value)
    }

    fun updateEnableTrivia(value: Boolean) {
        _uiState.value = _uiState.value.copy(enableTrivia = value)
    }

    fun create(onCreated: (Int) -> Unit) {
        val state = _uiState.value
        if (state.name.isBlank()) {
            _uiState.value = state.copy(error = "Game name is required.")
            return
        }
        viewModelScope.launch {
            _uiState.value = state.copy(isLoading = true, error = null)
            repository.createSession(
                name = state.name.trim(),
                mode = state.mode.raw,
                maxSongs = state.maxSongs,
                secondsPerSong = state.secondsPerSong,
                enableTrivia = state.enableTrivia,
            ).onSuccess { detail ->
                _uiState.value = state.copy(isLoading = false)
                onCreated(detail.id)
            }.onFailure { throwable ->
                _uiState.value = state.copy(
                    isLoading = false,
                    error = throwable.humanReadableMessage(),
                )
            }
        }
    }
}
