package fm.tunetrivia.mobile.ui.session.home

import androidx.compose.runtime.State
import androidx.compose.runtime.mutableStateOf
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.juke.core.network.humanReadableMessage
import fm.tunetrivia.mobile.core.di.ServiceLocator
import fm.tunetrivia.mobile.data.repository.TuneTriviaRepository
import fm.tunetrivia.mobile.model.TuneTriviaSession
import kotlinx.coroutines.launch

data class HomeUiState(
    val isLoading: Boolean = true,
    val sessions: List<TuneTriviaSession> = emptyList(),
    val error: String? = null,
)

class HomeViewModel(
    private val repository: TuneTriviaRepository = ServiceLocator.tuneTriviaRepository,
) : ViewModel() {
    private val _uiState = mutableStateOf(HomeUiState())
    val uiState: State<HomeUiState> = _uiState

    init {
        loadSessions()
    }

    fun loadSessions() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            repository.getMySessions()
                .onSuccess { sessions ->
                    _uiState.value = HomeUiState(isLoading = false, sessions = sessions)
                }
                .onFailure { throwable ->
                    _uiState.value = HomeUiState(
                        isLoading = false,
                        sessions = emptyList(),
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }
}
