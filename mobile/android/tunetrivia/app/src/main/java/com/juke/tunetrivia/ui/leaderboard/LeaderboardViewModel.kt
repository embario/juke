package com.juke.tunetrivia.ui.leaderboard

import androidx.compose.runtime.State
import androidx.compose.runtime.mutableStateOf
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.juke.core.network.humanReadableMessage
import com.juke.tunetrivia.core.di.ServiceLocator
import com.juke.tunetrivia.data.repository.TuneTriviaRepository
import com.juke.tunetrivia.model.LeaderboardEntry
import kotlinx.coroutines.launch

data class LeaderboardUiState(
    val isLoading: Boolean = true,
    val entries: List<LeaderboardEntry> = emptyList(),
    val error: String? = null,
)

class LeaderboardViewModel(
    private val repository: TuneTriviaRepository = ServiceLocator.tuneTriviaRepository,
) : ViewModel() {
    private val _uiState = mutableStateOf(LeaderboardUiState())
    val uiState: State<LeaderboardUiState> = _uiState

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            repository.leaderboard()
                .onSuccess { entries ->
                    _uiState.value = LeaderboardUiState(isLoading = false, entries = entries)
                }
                .onFailure { throwable ->
                    _uiState.value = LeaderboardUiState(
                        isLoading = false,
                        entries = emptyList(),
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }
}
