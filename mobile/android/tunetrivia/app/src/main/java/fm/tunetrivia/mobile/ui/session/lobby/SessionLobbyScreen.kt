package fm.tunetrivia.mobile.ui.session.lobby

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.background
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import fm.tunetrivia.mobile.core.design.TuneTriviaPalette
import fm.tunetrivia.mobile.core.design.components.TuneTriviaBackground
import fm.tunetrivia.mobile.core.design.components.TuneTriviaButton
import fm.tunetrivia.mobile.core.design.components.TuneTriviaButtonVariant
import fm.tunetrivia.mobile.core.design.components.TuneTriviaCard
import fm.tunetrivia.mobile.core.design.components.TuneTriviaInputField
import fm.tunetrivia.mobile.core.design.components.TuneTriviaSpinner
import fm.tunetrivia.mobile.core.design.components.TuneTriviaStatusBanner
import fm.tunetrivia.mobile.core.design.components.TuneTriviaStatusVariant
import fm.tunetrivia.mobile.model.SessionMode
import fm.tunetrivia.mobile.model.SessionStatus
import fm.tunetrivia.mobile.model.TuneTriviaPlayer
import fm.tunetrivia.mobile.model.TuneTriviaRound

@Composable
fun SessionLobbyScreen(
    sessionId: Int,
    currentUsername: String,
    onBack: () -> Unit,
    onStartGame: () -> Unit,
    onAddTracks: (Int) -> Unit,
    viewModel: SessionLobbyViewModel = viewModel(),
) {
    val state by viewModel.uiState
    var showAddPlayer by remember { mutableStateOf(false) }
    var newPlayerName by remember { mutableStateOf("") }

    LaunchedEffect(sessionId) {
        viewModel.load(sessionId)
        viewModel.startPolling(sessionId)
    }

    DisposableEffect(Unit) {
        onDispose { viewModel.stopPolling() }
    }

    TuneTriviaBackground(modifier = Modifier.fillMaxSize()) {
        if (state.isLoading && state.session == null) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                TuneTriviaSpinner()
            }
            return@TuneTriviaBackground
        }

        val detail = state.session
        Box(modifier = Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 24.dp)
                    .systemBarsPadding()
                    .padding(top = 12.dp, bottom = 120.dp),
                verticalArrangement = Arrangement.spacedBy(20.dp),
            ) {
                TextButton(onClick = onBack, contentPadding = PaddingValues(0.dp)) {
                    Text(text = "Back", color = TuneTriviaPalette.Secondary)
                }

                state.error?.let {
                    TuneTriviaStatusBanner(message = it, variant = TuneTriviaStatusVariant.ERROR)
                }

                val safeDetail = detail ?: return@Box
                val isHost = safeDetail.hostUsername == currentUsername

                TuneTriviaCard(accentColor = TuneTriviaPalette.Accent) {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(
                            text = safeDetail.name,
                            style = MaterialTheme.typography.titleLarge,
                            color = TuneTriviaPalette.Text,
                        )
                        Text(
                            text = safeDetail.code,
                            style = MaterialTheme.typography.headlineLarge,
                            color = TuneTriviaPalette.Accent,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = "Share this code with your friends",
                            style = MaterialTheme.typography.bodySmall,
                            color = TuneTriviaPalette.Muted,
                        )
                    }
                }

                TuneTriviaCard(accentColor = TuneTriviaPalette.Secondary) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        InfoPill(label = "${safeDetail.maxSongs} songs")
                        InfoPill(label = "${safeDetail.secondsPerSong}s each")
                        InfoPill(label = if (safeDetail.mode == SessionMode.HOST) "Host Mode" else "Party Mode")
                    }
                }

                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = "Players (${safeDetail.players.size})",
                            style = MaterialTheme.typography.titleMedium,
                            color = TuneTriviaPalette.Text,
                        )
                        if (isHost && safeDetail.mode == SessionMode.HOST) {
                            TextButton(onClick = { showAddPlayer = true }) {
                                Text(text = "Add Player", color = TuneTriviaPalette.Accent)
                            }
                        }
                    }

                    if (safeDetail.players.isEmpty()) {
                        TuneTriviaCard {
                            Text(
                                text = "No players yet. Share the code!",
                                style = MaterialTheme.typography.bodyMedium,
                                color = TuneTriviaPalette.Muted,
                            )
                        }
                    } else {
                        safeDetail.players.forEach { player ->
                            PlayerRow(player)
                        }
                    }
                }

                if (isHost) {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                text = "Tracks (${safeDetail.rounds.size}/${safeDetail.maxSongs})",
                                style = MaterialTheme.typography.titleMedium,
                                color = TuneTriviaPalette.Text,
                            )
                            TextButton(onClick = {
                                val remaining = safeDetail.maxSongs - safeDetail.rounds.size
                                onAddTracks(remaining)
                            }) {
                                Text(text = "Add Tracks", color = TuneTriviaPalette.Accent)
                            }
                        }

                        if (safeDetail.rounds.isEmpty()) {
                            TuneTriviaCard {
                                Text(
                                    text = "Add some tracks to get started!",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = TuneTriviaPalette.Muted,
                                )
                            }
                        } else {
                            safeDetail.rounds.take(5).forEach { round ->
                                TrackRow(round)
                            }
                            if (safeDetail.rounds.size > 5) {
                                Text(
                                    text = "+ ${safeDetail.rounds.size - 5} more tracks",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = TuneTriviaPalette.Muted,
                                )
                            }
                        }
                    }
                }
            }

            val canStart = detail?.let { it.rounds.isNotEmpty() && it.players.isNotEmpty() } == true
            if (detail != null) {
                Column(
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                        .padding(horizontal = 24.dp)
                        .padding(bottom = 20.dp),
                ) {
                    if (detail.status == SessionStatus.LOBBY && detail.hostUsername == currentUsername) {
                        TuneTriviaButton(
                            onClick = { viewModel.startGame(sessionId, onStartGame) },
                            enabled = canStart && !state.isStarting,
                        ) {
                            Text(text = if (state.isStarting) "Starting..." else "Start Game")
                        }
                    } else if (detail.status == SessionStatus.LOBBY) {
                        TuneTriviaCard {
                            Text(
                                text = "Waiting for host to start...",
                                style = MaterialTheme.typography.bodyMedium,
                                color = TuneTriviaPalette.Muted,
                            )
                        }
                    }
                }
            }
        }

        if (showAddPlayer) {
            AlertDialog(
                onDismissRequest = { showAddPlayer = false },
                title = { Text(text = "Add Player") },
                text = {
                    TuneTriviaInputField(
                        label = "Player Name",
                        value = newPlayerName,
                        onValueChange = { newPlayerName = it },
                        placeholder = "Enter name",
                    )
                },
                confirmButton = {
                    TextButton(
                        onClick = {
                            viewModel.addPlayer(sessionId, newPlayerName) {
                                newPlayerName = ""
                                showAddPlayer = false
                            }
                        },
                    ) {
                        Text("Add")
                    }
                },
                dismissButton = {
                    TextButton(onClick = { showAddPlayer = false }) {
                        Text("Cancel")
                    }
                },
            )
        }
    }
}

@Composable
private fun InfoPill(label: String) {
    Box(
        modifier = Modifier
            .background(
                color = TuneTriviaPalette.PanelAlt,
                shape = RoundedCornerShape(999.dp),
            )
            .padding(horizontal = 10.dp, vertical = 6.dp),
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = TuneTriviaPalette.Text,
        )
    }
}

@Composable
private fun PlayerRow(player: TuneTriviaPlayer) {
    TuneTriviaCard(backgroundColors = listOf(TuneTriviaPalette.PanelAlt, TuneTriviaPalette.Panel)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    text = player.displayName,
                    style = MaterialTheme.typography.bodyMedium,
                    color = TuneTriviaPalette.Text,
                )
                if (player.isHost) {
                    Text(
                        text = "Host",
                        style = MaterialTheme.typography.bodySmall,
                        color = TuneTriviaPalette.Accent,
                    )
                }
            }
            Text(
                text = "${player.totalScore} pts",
                style = MaterialTheme.typography.bodySmall,
                color = TuneTriviaPalette.Muted,
            )
        }
    }
}

@Composable
private fun TrackRow(round: TuneTriviaRound) {
    TuneTriviaCard(backgroundColors = listOf(TuneTriviaPalette.PanelAlt, TuneTriviaPalette.Panel)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    text = round.trackName,
                    style = MaterialTheme.typography.bodyMedium,
                    color = TuneTriviaPalette.Text,
                )
                Text(
                    text = round.artistName,
                    style = MaterialTheme.typography.bodySmall,
                    color = TuneTriviaPalette.Muted,
                )
            }
            Text(
                text = "#${round.roundNumber}",
                style = MaterialTheme.typography.bodySmall,
                color = TuneTriviaPalette.Muted,
            )
        }
    }
}
