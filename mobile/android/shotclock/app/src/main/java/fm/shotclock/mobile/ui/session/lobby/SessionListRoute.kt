package fm.shotclock.mobile.ui.session.lobby

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import fm.shotclock.mobile.core.design.ShotClockPalette
import fm.shotclock.mobile.core.design.components.SCButtonVariant
import fm.shotclock.mobile.core.design.components.SCStatusVariant
import fm.shotclock.mobile.core.design.components.ShotClockButton
import fm.shotclock.mobile.core.design.components.ShotClockCard
import fm.shotclock.mobile.core.design.components.ShotClockInputField
import fm.shotclock.mobile.core.design.components.ShotClockSpinner
import fm.shotclock.mobile.core.design.components.ShotClockStatusBanner
import fm.shotclock.mobile.core.di.ServiceLocator
import fm.juke.core.session.SessionSnapshot
import fm.juke.core.network.humanReadableMessage
import fm.shotclock.mobile.data.repository.PowerHourRepository
import fm.shotclock.mobile.model.PowerHourSession
import fm.shotclock.mobile.model.SessionStatus
import fm.shotclock.mobile.ui.session.create.CreateSessionScreen
import fm.shotclock.mobile.ui.session.ended.SessionEndScreen
import fm.shotclock.mobile.ui.session.playback.PlaybackScreen
import fm.shotclock.mobile.ui.session.playback.PlaybackViewModel
import fm.shotclock.mobile.ui.session.tracks.AddTracksScreen
import fm.shotclock.mobile.ui.session.tracks.AddTracksViewModel
import kotlinx.coroutines.launch

// ---------------------------------------------------------------------------
// Navigation state
// ---------------------------------------------------------------------------

private sealed interface SessionScreen {
    data object List : SessionScreen
    data object Create : SessionScreen
    data class Lobby(val sessionId: String) : SessionScreen
    data class AddTracks(val sessionId: String) : SessionScreen
    data class Playback(val sessionId: String) : SessionScreen
    data class Ended(val sessionId: String) : SessionScreen
}

// ---------------------------------------------------------------------------
// SessionListViewModel
// ---------------------------------------------------------------------------

data class SessionListUiState(
    val isLoading: Boolean = true,
    val sessions: List<PowerHourSession> = emptyList(),
    val error: String? = null,
    val isJoining: Boolean = false,
    val joinError: String? = null,
)

class SessionListViewModel(
    private val repository: PowerHourRepository = ServiceLocator.powerHourRepository,
) : ViewModel() {

    var uiState by mutableStateOf(SessionListUiState())
        private set

    init {
        listSessions()
    }

    fun listSessions() {
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            repository.listSessions()
                .onSuccess { sessions ->
                    uiState = uiState.copy(isLoading = false, sessions = sessions)
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(
                        isLoading = false,
                        error = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    fun refresh() = listSessions()

    fun joinSession(inviteCode: String, onSuccess: (PowerHourSession) -> Unit) {
        if (inviteCode.isBlank()) {
            uiState = uiState.copy(joinError = "Invite code is required.")
            return
        }
        viewModelScope.launch {
            uiState = uiState.copy(isJoining = true, joinError = null)
            repository.joinSession(inviteCode.trim())
                .onSuccess { session ->
                    uiState = uiState.copy(isJoining = false)
                    onSuccess(session)
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(
                        isJoining = false,
                        joinError = throwable.humanReadableMessage(),
                    )
                }
        }
    }

    fun clearJoinError() {
        uiState = uiState.copy(joinError = null)
    }
}

// ---------------------------------------------------------------------------
// Route (navigation host)
// ---------------------------------------------------------------------------

@Composable
fun SessionListRoute(
    session: SessionSnapshot,
    listViewModel: SessionListViewModel = viewModel(),
) {
    var currentScreen by rememberSaveable { mutableStateOf<String>("list") }
    var activeSessionId by rememberSaveable { mutableStateOf<String?>(null) }

    // Decode simple string-based screen state (survives config change via rememberSaveable)
    val screen: SessionScreen = when {
        currentScreen == "create" -> SessionScreen.Create
        currentScreen == "lobby" && activeSessionId != null -> SessionScreen.Lobby(activeSessionId!!)
        currentScreen == "addTracks" && activeSessionId != null -> SessionScreen.AddTracks(activeSessionId!!)
        currentScreen == "playback" && activeSessionId != null -> SessionScreen.Playback(activeSessionId!!)
        currentScreen == "ended" && activeSessionId != null -> SessionScreen.Ended(activeSessionId!!)
        else -> SessionScreen.List
    }

    fun navigateTo(s: SessionScreen) {
        when (s) {
            SessionScreen.List -> {
                currentScreen = "list"
                activeSessionId = null
            }
            SessionScreen.Create -> {
                currentScreen = "create"
            }
            is SessionScreen.Lobby -> {
                currentScreen = "lobby"
                activeSessionId = s.sessionId
            }
            is SessionScreen.AddTracks -> {
                currentScreen = "addTracks"
                activeSessionId = s.sessionId
            }
            is SessionScreen.Playback -> {
                currentScreen = "playback"
                activeSessionId = s.sessionId
            }
            is SessionScreen.Ended -> {
                currentScreen = "ended"
                activeSessionId = s.sessionId
            }
        }
    }

    when (val s = screen) {
        SessionScreen.List -> {
            SessionListScreen(
                viewModel = listViewModel,
                onNavigateToCreate = { navigateTo(SessionScreen.Create) },
                onNavigateToLobby = { sessionId ->
                    navigateTo(SessionScreen.Lobby(sessionId))
                },
            )
        }
        SessionScreen.Create -> {
            CreateSessionScreen(
                onNavigateBack = {
                    navigateTo(SessionScreen.List)
                },
                onSessionCreated = { createdSession ->
                    listViewModel.refresh()
                    navigateTo(SessionScreen.Lobby(createdSession.id))
                },
            )
        }
        is SessionScreen.Lobby -> {
            val lobbyVm = remember(s.sessionId) {
                SessionLobbyViewModel(
                    sessionId = s.sessionId,
                    currentUsername = session.username,
                )
            }
            SessionLobbyScreen(
                viewModel = lobbyVm,
                onNavigateBack = {
                    listViewModel.refresh()
                    navigateTo(SessionScreen.List)
                },
                onNavigateToAddTracks = {
                    navigateTo(SessionScreen.AddTracks(s.sessionId))
                },
                onNavigateToPlayback = {
                    navigateTo(SessionScreen.Playback(s.sessionId))
                },
                onNavigateToEnded = {
                    navigateTo(SessionScreen.Ended(s.sessionId))
                },
            )
        }
        is SessionScreen.AddTracks -> {
            val addTracksVm = remember(s.sessionId) {
                AddTracksViewModel(sessionId = s.sessionId)
            }
            AddTracksScreen(
                viewModel = addTracksVm,
                onNavigateBack = {
                    navigateTo(SessionScreen.Lobby(s.sessionId))
                },
            )
        }
        is SessionScreen.Playback -> {
            val playbackVm = remember(s.sessionId) {
                PlaybackViewModel(
                    sessionId = s.sessionId,
                    currentUsername = session.username,
                )
            }
            PlaybackScreen(
                viewModel = playbackVm,
                onNavigateToEnded = {
                    navigateTo(SessionScreen.Ended(s.sessionId))
                },
            )
        }
        is SessionScreen.Ended -> {
            SessionEndScreen(
                sessionId = s.sessionId,
                onNavigateBack = {
                    listViewModel.refresh()
                    navigateTo(SessionScreen.List)
                },
            )
        }
    }
}

// ---------------------------------------------------------------------------
// Session list screen
// ---------------------------------------------------------------------------

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SessionListScreen(
    viewModel: SessionListViewModel,
    onNavigateToCreate: () -> Unit,
    onNavigateToLobby: (String) -> Unit,
) {
    val state = viewModel.uiState
    var showJoinSheet by remember { mutableStateOf(false) }
    var joinCode by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    // Pull-to-refresh via LaunchedEffect on composition
    LaunchedEffect(Unit) {
        viewModel.refresh()
    }

    // Join bottom sheet
    if (showJoinSheet) {
        val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
        ModalBottomSheet(
            onDismissRequest = {
                showJoinSheet = false
                joinCode = ""
                viewModel.clearJoinError()
            },
            sheetState = sheetState,
            containerColor = ShotClockPalette.Panel,
            contentColor = ShotClockPalette.Text,
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 24.dp)
                    .padding(bottom = 32.dp),
            ) {
                Text(
                    text = "Join with Code",
                    style = MaterialTheme.typography.headlineSmall,
                    color = ShotClockPalette.Text,
                )
                Spacer(modifier = Modifier.height(16.dp))

                ShotClockStatusBanner(
                    message = state.joinError,
                    variant = SCStatusVariant.ERROR,
                )
                if (state.joinError != null) Spacer(modifier = Modifier.height(12.dp))

                ShotClockInputField(
                    label = "Invite Code",
                    value = joinCode,
                    onValueChange = {
                        joinCode = it
                        viewModel.clearJoinError()
                    },
                    placeholder = "Enter invite code",
                )

                Spacer(modifier = Modifier.height(20.dp))

                if (state.isJoining) {
                    Box(
                        modifier = Modifier.fillMaxWidth(),
                        contentAlignment = Alignment.Center,
                    ) {
                        ShotClockSpinner()
                    }
                } else {
                    ShotClockButton(
                        onClick = {
                            viewModel.joinSession(joinCode) { joined ->
                                showJoinSheet = false
                                joinCode = ""
                                viewModel.refresh()
                                onNavigateToLobby(joined.id)
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                        variant = SCButtonVariant.PRIMARY,
                        enabled = joinCode.isNotBlank(),
                    ) {
                        Text(text = "Join Session")
                    }
                }
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 24.dp),
    ) {
        Spacer(modifier = Modifier.height(8.dp))

        // Action buttons
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            ShotClockButton(
                onClick = onNavigateToCreate,
                modifier = Modifier.weight(1f),
                variant = SCButtonVariant.PRIMARY,
            ) {
                Text(text = "New Session")
            }
            ShotClockButton(
                onClick = { showJoinSheet = true },
                modifier = Modifier.weight(1f),
                variant = SCButtonVariant.GHOST,
            ) {
                Text(text = "Join with Code")
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // Error banner
        ShotClockStatusBanner(
            message = state.error,
            variant = SCStatusVariant.ERROR,
        )
        if (state.error != null) Spacer(modifier = Modifier.height(12.dp))

        // Content
        when {
            state.isLoading -> {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    contentAlignment = Alignment.Center,
                ) {
                    ShotClockSpinner()
                }
            }
            state.sessions.isEmpty() -> {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    contentAlignment = Alignment.Center,
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            text = "No sessions yet",
                            style = MaterialTheme.typography.titleLarge,
                            color = ShotClockPalette.Muted,
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Create a new session or join one with a code.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = ShotClockPalette.Muted.copy(alpha = 0.7f),
                        )
                    }
                }
            }
            else -> {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(
                        bottom = 16.dp,
                    ),
                ) {
                    items(state.sessions, key = { it.id }) { sessionItem ->
                        SessionCard(
                            session = sessionItem,
                            onClick = { onNavigateToLobby(sessionItem.id) },
                        )
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Session card
// ---------------------------------------------------------------------------

@Composable
private fun SessionCard(
    session: PowerHourSession,
    onClick: () -> Unit,
) {
    ShotClockCard(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Top,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = session.title,
                    style = MaterialTheme.typography.titleLarge,
                    color = ShotClockPalette.Text,
                    maxLines = 1,
                )
                Spacer(modifier = Modifier.height(6.dp))
                Row(
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = "${session.playerCount} players",
                        style = MaterialTheme.typography.bodySmall,
                        color = ShotClockPalette.Muted,
                    )
                    Text(
                        text = "${session.trackCount} tracks",
                        style = MaterialTheme.typography.bodySmall,
                        color = ShotClockPalette.Muted,
                    )
                }
            }
            Spacer(modifier = Modifier.width(12.dp))
            // Status dot + label
            Row(verticalAlignment = Alignment.CenterVertically) {
                val statusColor = when (session.status) {
                    SessionStatus.LOBBY -> ShotClockPalette.Secondary
                    SessionStatus.ACTIVE -> ShotClockPalette.Success
                    SessionStatus.PAUSED -> ShotClockPalette.Warning
                    SessionStatus.ENDED -> ShotClockPalette.Muted
                }
                Box(
                    modifier = Modifier
                        .size(10.dp)
                        .shadow(4.dp, CircleShape, ambientColor = statusColor.copy(alpha = 0.5f))
                        .clip(CircleShape)
                        .background(statusColor),
                )
                Spacer(modifier = Modifier.width(6.dp))
                Text(
                    text = session.status.label,
                    style = MaterialTheme.typography.labelLarge.copy(
                        fontWeight = FontWeight.Medium,
                    ),
                    color = statusColor,
                )
            }
        }
    }
}
