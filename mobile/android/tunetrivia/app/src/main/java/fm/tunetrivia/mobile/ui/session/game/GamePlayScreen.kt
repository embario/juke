package fm.tunetrivia.mobile.ui.session.game

import android.media.MediaPlayer
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
import fm.tunetrivia.mobile.model.RoundStatus
import fm.tunetrivia.mobile.model.SessionMode
import fm.tunetrivia.mobile.model.SessionStatus
import fm.tunetrivia.mobile.model.TuneTriviaPlayer
import fm.tunetrivia.mobile.model.TuneTriviaRound

@Composable
fun GamePlayScreen(
    sessionId: Int,
    currentUsername: String,
    onBack: () -> Unit,
    viewModel: GamePlayViewModel = viewModel(),
) {
    val state by viewModel.uiState
    var showScoreboard by remember { mutableStateOf(false) }
    var songGuess by remember { mutableStateOf("") }
    var artistGuess by remember { mutableStateOf("") }
    var selectedTrivia by remember { mutableStateOf<String?>(null) }
    var hasSubmittedGuess by remember { mutableStateOf(false) }
    var hasSubmittedTrivia by remember { mutableStateOf(false) }

    LaunchedEffect(sessionId) {
        viewModel.load(sessionId)
        viewModel.startPolling(sessionId)
    }

    DisposableEffect(Unit) {
        onDispose { viewModel.stopPolling() }
    }

    val detail = state.session
    val isHost = detail?.hostUsername == currentUsername
    val currentRound = detail?.rounds?.firstOrNull { it.status == RoundStatus.PLAYING || it.status == RoundStatus.REVEALED }
        ?: detail?.rounds?.lastOrNull()

    LaunchedEffect(currentRound?.id) {
        songGuess = ""
        artistGuess = ""
        selectedTrivia = null
        hasSubmittedGuess = false
        hasSubmittedTrivia = false
    }

    TuneTriviaBackground(modifier = Modifier.fillMaxSize()) {
        if (state.isLoading && detail == null) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                TuneTriviaSpinner()
            }
            return@TuneTriviaBackground
        }

        if (detail?.status == SessionStatus.FINISHED) {
            FinalScoreboard(detail.players, detail.name, onBack)
            return@TuneTriviaBackground
        }

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

            if (detail == null || currentRound == null) {
                TuneTriviaCard {
                    Text(
                        text = "Waiting for next round...",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TuneTriviaPalette.Muted,
                    )
                }
                return@Column
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    text = "Round ${currentRound.roundNumber} of ${detail.maxSongs}",
                    style = MaterialTheme.typography.titleMedium,
                    color = TuneTriviaPalette.Text,
                )
                Text(
                    text = currentRound.status.raw.replaceFirstChar { it.uppercase() },
                    style = MaterialTheme.typography.bodySmall,
                    color = TuneTriviaPalette.Muted,
                )
            }

            TuneTriviaCard(accentColor = if (currentRound.status == RoundStatus.REVEALED) TuneTriviaPalette.Secondary else TuneTriviaPalette.Accent) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        text = if (currentRound.status == RoundStatus.REVEALED) {
                            currentRound.trackName
                        } else {
                            "Mystery Track"
                        },
                        style = MaterialTheme.typography.titleLarge,
                        color = TuneTriviaPalette.Text,
                    )
                    Text(
                        text = if (currentRound.status == RoundStatus.REVEALED) {
                            currentRound.artistName
                        } else {
                            "Make your guess!"
                        },
                        style = MaterialTheme.typography.bodyMedium,
                        color = TuneTriviaPalette.Muted,
                    )
                }
            }

            if (currentRound.status == RoundStatus.PLAYING && currentRound.previewUrl != null) {
                AudioControls(currentRound.previewUrl)
            }

            if (!isHost && currentRound.status == RoundStatus.PLAYING) {
                if (!hasSubmittedGuess) {
                    TuneTriviaCard {
                        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            Text(
                                text = "Your Guess",
                                style = MaterialTheme.typography.titleMedium,
                                color = TuneTriviaPalette.Text,
                            )
                            TuneTriviaInputField(
                                label = "Song Title",
                                value = songGuess,
                                onValueChange = { songGuess = it },
                                placeholder = "What song is this?",
                            )
                            TuneTriviaInputField(
                                label = "Artist",
                                value = artistGuess,
                                onValueChange = { artistGuess = it },
                                placeholder = "Who sings it?",
                            )
                            TuneTriviaButton(
                                onClick = {
                                    viewModel.submitGuess(
                                        currentRound.id,
                                        songGuess.ifBlank { null },
                                        artistGuess.ifBlank { null },
                                        onSuccess = { hasSubmittedGuess = true },
                                    )
                                },
                                enabled = (songGuess.isNotBlank() || artistGuess.isNotBlank()) && !state.isSubmittingGuess,
                            ) {
                                Text(text = if (state.isSubmittingGuess) "Submitting..." else "Submit Guess")
                            }
                        }
                    }
                } else {
                    TuneTriviaCard(accentColor = TuneTriviaPalette.Secondary) {
                        Text(
                            text = "Guess submitted! Waiting for reveal...",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TuneTriviaPalette.Text,
                        )
                    }
                }
            }

            if (currentRound.status == RoundStatus.REVEALED && currentRound.hasTrivia) {
                TriviaSection(
                    round = currentRound,
                    canAnswer = !isHost && detail.mode == SessionMode.PARTY,
                    selected = selectedTrivia,
                    onSelect = { selectedTrivia = it },
                    onSubmit = {
                        selectedTrivia?.let {
                            viewModel.submitTrivia(
                                currentRound.id,
                                it,
                                onSuccess = { hasSubmittedTrivia = true },
                            )
                        }
                    },
                    result = state.triviaResult,
                    isSubmitting = state.isSubmittingTrivia,
                    hasSubmitted = hasSubmittedTrivia,
                )
            }

            if (isHost && detail.mode == SessionMode.HOST && currentRound.status == RoundStatus.REVEALED) {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(
                        text = "Award Points",
                        style = MaterialTheme.typography.titleMedium,
                        color = TuneTriviaPalette.Text,
                    )
                    detail.players.filter { !it.isHost }.forEach { player ->
                        AwardRow(player) { points ->
                            viewModel.awardPoints(player.id, points)
                        }
                    }
                }
            }

            if (isHost) {
                TuneTriviaCard {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(
                            text = "Host Controls",
                            style = MaterialTheme.typography.titleMedium,
                            color = TuneTriviaPalette.Text,
                        )
                        if (currentRound.status == RoundStatus.PLAYING) {
                            TuneTriviaButton(
                                onClick = { viewModel.revealRound(sessionId) },
                                variant = TuneTriviaButtonVariant.SECONDARY,
                            ) {
                                Text(text = "Reveal Answer")
                            }
                        } else if (currentRound.status == RoundStatus.REVEALED) {
                            TuneTriviaButton(
                                onClick = { viewModel.nextRound(sessionId) },
                                enabled = !state.isAdvancing,
                            ) {
                                Text(text = if (state.isAdvancing) "Advancing..." else "Next Round")
                            }
                        }
                        TuneTriviaButton(
                            onClick = { viewModel.endGame(sessionId) },
                            variant = TuneTriviaButtonVariant.DESTRUCTIVE,
                            enabled = !state.isEnding,
                        ) {
                            Text(text = if (state.isEnding) "Ending..." else "End Game")
                        }
                    }
                }
            }

            TuneTriviaButton(
                onClick = { showScoreboard = true },
                variant = TuneTriviaButtonVariant.LINK,
            ) {
                Text(text = "View Scoreboard")
            }
        }

        if (showScoreboard && detail != null) {
            AlertDialog(
                onDismissRequest = { showScoreboard = false },
                title = { Text("Scoreboard") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        detail.players.sortedByDescending { it.totalScore }.forEachIndexed { index, player ->
                            Text("#${index + 1} ${player.displayName} - ${player.totalScore} pts")
                        }
                    }
                },
                confirmButton = {
                    TextButton(onClick = { showScoreboard = false }) {
                        Text("Close")
                    }
                },
            )
        }
    }
}

@Composable
private fun AudioControls(previewUrl: String) {
    var isPlaying by remember { mutableStateOf(false) }
    var player: MediaPlayer? by remember { mutableStateOf(null) }

    DisposableEffect(previewUrl) {
        onDispose {
            player?.release()
            player = null
        }
    }

    TuneTriviaCard {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                text = if (isPlaying) "Playing..." else "Tap to play preview",
                style = MaterialTheme.typography.bodyMedium,
                color = TuneTriviaPalette.Muted,
            )
            TuneTriviaButton(
                onClick = {
                    if (isPlaying) {
                        player?.pause()
                        isPlaying = false
                    } else {
                        if (player == null) {
                            player = MediaPlayer().apply {
                                setDataSource(previewUrl)
                                setOnPreparedListener {
                                    start()
                                    isPlaying = true
                                }
                                prepareAsync()
                            }
                        } else {
                            player?.start()
                            isPlaying = true
                        }
                    }
                },
                variant = TuneTriviaButtonVariant.SECONDARY,
            ) {
                Text(text = if (isPlaying) "Pause" else "Play")
            }
        }
    }
}

@Composable
private fun TriviaSection(
    round: TuneTriviaRound,
    canAnswer: Boolean,
    selected: String?,
    onSelect: (String) -> Unit,
    onSubmit: () -> Unit,
    result: fm.tunetrivia.mobile.model.TriviaResult?,
    isSubmitting: Boolean,
    hasSubmitted: Boolean,
) {
    TuneTriviaCard(accentColor = TuneTriviaPalette.Highlight) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Text(
                    text = "Bonus Trivia",
                    style = MaterialTheme.typography.titleMedium,
                    color = TuneTriviaPalette.Text,
                )
                Text(
                    text = "+50 pts",
                    style = MaterialTheme.typography.bodySmall,
                    color = TuneTriviaPalette.Highlight,
                    fontWeight = FontWeight.Bold,
                )
            }
            Text(
                text = round.triviaQuestion ?: "",
                style = MaterialTheme.typography.bodyMedium,
                color = TuneTriviaPalette.Text,
            )
            val options = round.triviaOptions ?: emptyList()
            options.forEach { option ->
                TuneTriviaButton(
                    onClick = { onSelect(option) },
                    variant = if (selected == option) TuneTriviaButtonVariant.SECONDARY else TuneTriviaButtonVariant.GHOST,
                ) {
                    Text(text = option)
                }
            }
            if (canAnswer && !hasSubmitted) {
                TuneTriviaButton(
                    onClick = onSubmit,
                    enabled = selected != null && !isSubmitting,
                ) {
                    Text(text = if (isSubmitting) "Submitting..." else "Submit Answer")
                }
            }
            if (hasSubmitted && result != null) {
                Text(
                    text = if (result.correct) "Correct! +${result.pointsEarned} pts" else "Incorrect!",
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (result.correct) TuneTriviaPalette.Secondary else TuneTriviaPalette.Accent,
                )
            }
        }
    }
}

@Composable
private fun AwardRow(player: TuneTriviaPlayer, onAward: (Int) -> Unit) {
    TuneTriviaCard {
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
                Text(
                    text = "${player.totalScore} pts",
                    style = MaterialTheme.typography.bodySmall,
                    color = TuneTriviaPalette.Muted,
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AwardChip(label = "+50") { onAward(50) }
                AwardChip(label = "+100") { onAward(100) }
                AwardChip(label = "+150") { onAward(150) }
            }
        }
    }
}

@Composable
private fun AwardChip(label: String, onClick: () -> Unit) {
    TuneTriviaButton(
        onClick = onClick,
        variant = TuneTriviaButtonVariant.GHOST,
        fillMaxWidth = false,
        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 6.dp),
    ) {
        Text(text = label)
    }
}

@Composable
private fun FinalScoreboard(players: List<TuneTriviaPlayer>, sessionName: String, onDone: () -> Unit) {
    val sorted = players.sortedByDescending { it.totalScore }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp)
            .systemBarsPadding()
            .padding(top = 40.dp, bottom = 40.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = "Game Over!",
            style = MaterialTheme.typography.headlineLarge,
            color = TuneTriviaPalette.Text,
        )
        Text(
            text = sessionName,
            style = MaterialTheme.typography.bodyMedium,
            color = TuneTriviaPalette.Muted,
        )

        sorted.firstOrNull()?.let { winner ->
            TuneTriviaCard(accentColor = TuneTriviaPalette.Highlight) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(text = "Winner", style = MaterialTheme.typography.bodySmall, color = TuneTriviaPalette.Muted)
                    Text(text = winner.displayName, style = MaterialTheme.typography.titleLarge, color = TuneTriviaPalette.Text)
                    Text(text = "${winner.totalScore} points", style = MaterialTheme.typography.titleMedium, color = TuneTriviaPalette.Highlight)
                }
            }
        }

        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            sorted.forEachIndexed { index, player ->
                TuneTriviaCard {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Text(text = "#${index + 1} ${player.displayName}", color = TuneTriviaPalette.Text)
                        Text(text = "${player.totalScore} pts", color = TuneTriviaPalette.Accent)
                    }
                }
            }
        }

        TuneTriviaButton(onClick = onDone) {
            Text(text = "Done")
        }
    }
}
