package fm.tunetrivia.mobile.ui.session.join

import androidx.compose.runtime.State
import androidx.compose.runtime.mutableStateOf
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.juke.core.network.humanReadableMessage
import fm.tunetrivia.mobile.core.di.ServiceLocator
import fm.tunetrivia.mobile.data.repository.TuneTriviaRepository
import kotlinx.coroutines.launch

data class JoinSessionUiState(
    val code: String = "",
    val displayName: String = "",
    val isLoading: Boolean = false,
    val error: String? = null,
)

class JoinSessionViewModel(
    private val repository: TuneTriviaRepository = ServiceLocator.tuneTriviaRepository,
) : ViewModel() {
    private val _uiState = mutableStateOf(JoinSessionUiState())
    val uiState: State<JoinSessionUiState> = _uiState

    fun updateCode(value: String) {
        val filtered = value.uppercase().take(6)
        _uiState.value = _uiState.value.copy(code = filtered, error = null)
    }

    fun updateDisplayName(value: String) {
        _uiState.value = _uiState.value.copy(displayName = value, error = null)
    }

    fun join(onJoined: (Int) -> Unit, needsDisplayName: Boolean) {
        val state = _uiState.value
        if (state.code.length != 6) {
            _uiState.value = state.copy(error = "Please enter a 6-character code.")
            return
        }
        if (needsDisplayName && state.displayName.isBlank()) {
            _uiState.value = state.copy(error = "Please enter your name.")
            return
        }
        viewModelScope.launch {
            _uiState.value = state.copy(isLoading = true, error = null)
            repository.joinSession(
                code = state.code,
                displayName = if (needsDisplayName) state.displayName else null,
            ).onSuccess { detail ->
                _uiState.value = state.copy(isLoading = false)
                onJoined(detail.id)
            }.onFailure { throwable ->
                _uiState.value = state.copy(
                    isLoading = false,
                    error = throwable.humanReadableMessage(),
                )
            }
        }
    }
}
