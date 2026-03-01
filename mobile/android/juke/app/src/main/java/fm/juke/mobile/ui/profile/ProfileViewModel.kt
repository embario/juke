package fm.juke.mobile.ui.profile

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.juke.mobile.core.di.ServiceLocator
import fm.juke.mobile.data.repository.ProfileRepository
import fm.juke.core.network.humanReadableMessage
import fm.juke.core.profile.MusicProfile
import fm.juke.core.profile.ProfileSummary
import kotlinx.coroutines.launch

data class ProfileUiState(
    val isLoading: Boolean = true,
    val profile: MusicProfile? = null,
    val focusedProfile: MusicProfile? = null,
    val searchQuery: String = "",
    val searchResults: List<ProfileSummary> = emptyList(),
    val error: String? = null,
)

class ProfileViewModel(
    private val repository: ProfileRepository = ServiceLocator.profileRepository,
) : ViewModel() {

    var uiState by mutableStateOf(ProfileUiState())
        private set

    init {
        refreshMyProfile()
    }

    fun refreshMyProfile() {
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            repository.fetchMyProfile()
                .onSuccess { profile ->
                    uiState = uiState.copy(isLoading = false, profile = profile, focusedProfile = profile)
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(isLoading = false, error = throwable.humanReadableMessage())
                }
        }
    }

    fun updateSearchQuery(value: String) {
        uiState = uiState.copy(searchQuery = value)
    }

    fun runProfileSearch() {
        val query = uiState.searchQuery.trim()
        if (query.length < 2) {
            uiState = uiState.copy(error = "Type at least two characters to search.")
            return
        }
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            repository.searchProfiles(query)
                .onSuccess { results ->
                    uiState = uiState.copy(isLoading = false, searchResults = results)
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(isLoading = false, error = throwable.humanReadableMessage())
                }
        }
    }

    fun focusOn(summary: ProfileSummary) {
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            repository.fetchProfile(summary.username)
                .onSuccess { profile ->
                    uiState = uiState.copy(isLoading = false, focusedProfile = profile)
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(isLoading = false, error = throwable.humanReadableMessage())
                }
        }
    }
}
