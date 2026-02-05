package fm.tunetrivia.mobile.ui.session

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.tunetrivia.mobile.core.di.ServiceLocator
import fm.tunetrivia.mobile.data.local.SessionSnapshot
import fm.tunetrivia.mobile.data.repository.AuthRepositoryContract
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface AppSessionUiState {
    data object Loading : AppSessionUiState
    data object SignedOut : AppSessionUiState
    data class SignedIn(val snapshot: SessionSnapshot) : AppSessionUiState
}

class AppSessionViewModel(
    private val repository: AuthRepositoryContract = ServiceLocator.authRepository,
) : ViewModel() {

    private val _uiState: MutableStateFlow<AppSessionUiState> = MutableStateFlow(AppSessionUiState.Loading)
    val uiState: StateFlow<AppSessionUiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            repository.session.collect { snapshot ->
                _uiState.value = snapshot?.let { AppSessionUiState.SignedIn(it) }
                    ?: AppSessionUiState.SignedOut
            }
        }
    }

    fun logout() {
        viewModelScope.launch {
            repository.logout()
        }
    }
}
