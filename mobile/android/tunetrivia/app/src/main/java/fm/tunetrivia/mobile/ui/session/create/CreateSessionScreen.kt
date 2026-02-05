package fm.tunetrivia.mobile.ui.session.create

import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
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

@Composable
fun CreateSessionScreen(
    onBack: () -> Unit,
    onCreated: (Int) -> Unit,
    viewModel: CreateSessionViewModel = viewModel(),
) {
    val state by viewModel.uiState

    TuneTriviaBackground(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp)
                .systemBarsPadding()
                .padding(top = 12.dp, bottom = 40.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            TextButton(onClick = onBack, contentPadding = PaddingValues(0.dp)) {
                Text(text = "Back", color = TuneTriviaPalette.Secondary)
            }

            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    text = "Create Game",
                    style = MaterialTheme.typography.headlineLarge,
                    color = TuneTriviaPalette.Text,
                )
                Text(
                    text = "Set up your Name That Tune game",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TuneTriviaPalette.Muted,
                )
            }

            if (state.error != null) {
                TuneTriviaStatusBanner(
                    message = state.error,
                    variant = TuneTriviaStatusVariant.ERROR,
                )
            }

            TuneTriviaCard {
                Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    TuneTriviaInputField(
                        label = "Game Name",
                        value = state.name,
                        onValueChange = viewModel::updateName,
                        placeholder = "Friday Night Trivia",
                    )

                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(
                            text = "Game Mode",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TuneTriviaPalette.Text,
                        )
                        ModeOption(
                            title = "Host Mode",
                            description = "You control scoring manually",
                            selected = state.mode == SessionMode.HOST,
                            onClick = { viewModel.updateMode(SessionMode.HOST) },
                        )
                        ModeOption(
                            title = "Party Mode",
                            description = "Players score themselves with codes",
                            selected = state.mode == SessionMode.PARTY,
                            onClick = { viewModel.updateMode(SessionMode.PARTY) },
                        )
                    }

                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(
                            text = "Number of Songs: ${state.maxSongs}",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TuneTriviaPalette.Text,
                        )
                        Slider(
                            value = state.maxSongs.toFloat(),
                            onValueChange = { viewModel.updateMaxSongs(it.toInt()) },
                            valueRange = 5f..30f,
                            steps = 24,
                        )
                    }

                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(
                            text = "Seconds per Song: ${state.secondsPerSong}",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TuneTriviaPalette.Text,
                        )
                        Slider(
                            value = state.secondsPerSong.toFloat(),
                            onValueChange = { value ->
                                val snapped = when {
                                    value < 15f -> 10
                                    value < 25f -> 20
                                    else -> 30
                                }
                                viewModel.updateSecondsPerSong(snapped)
                            },
                            valueRange = 10f..30f,
                            steps = 3,
                        )
                    }

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(
                                text = "Bonus Trivia",
                                style = MaterialTheme.typography.bodyMedium,
                                color = TuneTriviaPalette.Text,
                            )
                            Text(
                                text = "Extra trivia question per round (+50 pts)",
                                style = MaterialTheme.typography.bodySmall,
                                color = TuneTriviaPalette.Muted,
                            )
                        }
                        Switch(
                            checked = state.enableTrivia,
                            onCheckedChange = viewModel::updateEnableTrivia,
                        )
                    }
                }
            }

            if (state.isLoading) {
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    TuneTriviaSpinner()
                }
            } else {
                TuneTriviaButton(
                    onClick = { viewModel.create(onCreated) },
                    enabled = state.name.isNotBlank(),
                ) {
                    Text(text = "Create Game")
                }
            }
        }
    }
}

@Composable
private fun ModeOption(
    title: String,
    description: String,
    selected: Boolean,
    onClick: () -> Unit,
) {
    val accent = if (selected) TuneTriviaPalette.Accent else TuneTriviaPalette.Border
    TuneTriviaCard(
        accentColor = if (selected) TuneTriviaPalette.Accent else null,
        backgroundColors = listOf(TuneTriviaPalette.PanelAlt, TuneTriviaPalette.Panel),
    ) {
        TextButton(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleMedium,
                    color = TuneTriviaPalette.Text,
                )
                Text(
                    text = description,
                    style = MaterialTheme.typography.bodySmall,
                    color = TuneTriviaPalette.Muted,
                )
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = if (selected) "Selected" else "Tap to choose",
                    style = MaterialTheme.typography.labelMedium,
                    color = if (selected) TuneTriviaPalette.Accent else TuneTriviaPalette.Muted,
                )
            }
        }
    }
}
