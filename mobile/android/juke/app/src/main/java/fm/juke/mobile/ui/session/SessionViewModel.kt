package fm.juke.mobile.ui.session

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.juke.mobile.core.di.ServiceLocator
import fm.juke.mobile.data.local.SessionSnapshot
import fm.juke.mobile.data.repository.AuthRepositoryContract
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch

sealed interface SessionUiState {
    data object Loading : SessionUiState
    data object SignedOut : SessionUiState
    data class SignedIn(val snapshot: SessionSnapshot, val onboardingCompleted: Boolean) : SessionUiState
}

class SessionViewModel(
    private val repository: AuthRepositoryContract = ServiceLocator.authRepository,
    private val sessionStore: fm.juke.mobile.data.local.SessionStore = ServiceLocator.sessionStore,
    private val profileRepository: fm.juke.mobile.data.repository.ProfileRepository = ServiceLocator.profileRepository,
) : ViewModel() {

    private val _uiState: MutableStateFlow<SessionUiState> = MutableStateFlow(SessionUiState.Loading)
    val uiState: StateFlow<SessionUiState> = _uiState.asStateFlow()
    private var isRefreshingProfile = false

    init {
        viewModelScope.launch {
            combine(repository.session, sessionStore.onboardingCompleted) { snapshot, completed ->
                Pair(snapshot, completed)
            }.collect { (snapshot, completed) ->
                if (snapshot == null) {
                    _uiState.value = SessionUiState.SignedOut
                    return@collect
                }
                if (completed == null) {
                    _uiState.value = SessionUiState.Loading
                    refreshOnboardingStatus()
                    return@collect
                }
                _uiState.value = SessionUiState.SignedIn(snapshot, completed == true)
            }
        }
    }

    private fun refreshOnboardingStatus() {
        if (isRefreshingProfile) return
        isRefreshingProfile = true
        viewModelScope.launch {
            profileRepository.fetchMyProfile()
                .onFailure { sessionStore.setOnboardingCompletedAt("") }
            isRefreshingProfile = false
        }
    }

    fun logout() {
        viewModelScope.launch {
            repository.logout()
        }
    }
}
