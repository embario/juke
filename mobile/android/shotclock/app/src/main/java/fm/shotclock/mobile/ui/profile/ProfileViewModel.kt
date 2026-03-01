package fm.shotclock.mobile.ui.profile

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.shotclock.mobile.core.di.ServiceLocator
import fm.juke.core.network.humanReadableMessage
import fm.shotclock.mobile.data.repository.ProfileRepository
import fm.shotclock.mobile.model.MusicProfile
import kotlinx.coroutines.launch

data class ProfileUiState(
    val isLoading: Boolean = true,
    val profile: MusicProfile? = null,
    val error: String? = null,
)

class ProfileViewModel(
    private val repository: ProfileRepository = ServiceLocator.profileRepository,
) : ViewModel() {

    var uiState by mutableStateOf(ProfileUiState())
        private set

    init {
        loadProfile()
    }

    fun loadProfile() {
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            repository.fetchMyProfile()
                .onSuccess { profile ->
                    uiState = uiState.copy(isLoading = false, profile = profile)
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(
                        isLoading = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }
}
