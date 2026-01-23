package fm.juke.mobile.ui.session

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.juke.mobile.core.di.ServiceLocator
import fm.juke.mobile.data.local.SessionSnapshot
import fm.juke.mobile.data.repository.AuthRepositoryContract
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface SessionUiState {
    data object Loading : SessionUiState
    data object SignedOut : SessionUiState
    data class SignedIn(val snapshot: SessionSnapshot) : SessionUiState
}

class SessionViewModel(
    private val repository: AuthRepositoryContract = ServiceLocator.authRepository,
) : ViewModel() {

    private val _uiState: MutableStateFlow<SessionUiState> = MutableStateFlow(SessionUiState.Loading)
    val uiState: StateFlow<SessionUiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            repository.session.collect { snapshot ->
                _uiState.value = snapshot?.let { SessionUiState.SignedIn(it) } ?: SessionUiState.SignedOut
            }
        }
    }

    fun logout() {
        viewModelScope.launch {
            repository.logout()
        }
    }
}
