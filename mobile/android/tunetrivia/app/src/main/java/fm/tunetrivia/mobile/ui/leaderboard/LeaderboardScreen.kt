package fm.tunetrivia.mobile.ui.leaderboard

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
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import fm.tunetrivia.mobile.core.design.TuneTriviaPalette
import fm.tunetrivia.mobile.core.design.components.TuneTriviaBackground
import fm.tunetrivia.mobile.core.design.components.TuneTriviaCard
import fm.tunetrivia.mobile.core.design.components.TuneTriviaSpinner
import fm.tunetrivia.mobile.core.design.components.TuneTriviaStatusBanner
import fm.tunetrivia.mobile.core.design.components.TuneTriviaStatusVariant
import fm.tunetrivia.mobile.model.LeaderboardEntry

@Composable
fun LeaderboardScreen(
    onBack: () -> Unit,
    viewModel: LeaderboardViewModel = viewModel(),
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
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            TextButton(onClick = onBack, contentPadding = PaddingValues(0.dp)) {
                Text(text = "Back", color = TuneTriviaPalette.Secondary)
            }

            Text(
                text = "Leaderboard",
                style = MaterialTheme.typography.headlineLarge,
                color = TuneTriviaPalette.Text,
            )

            when {
                state.isLoading -> TuneTriviaSpinner()
                state.error != null -> TuneTriviaStatusBanner(
                    message = state.error,
                    variant = TuneTriviaStatusVariant.ERROR,
                )
                state.entries.isEmpty() -> TuneTriviaCard {
                    Text(
                        text = "No scores yet",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TuneTriviaPalette.Muted,
                    )
                }
                else -> {
                    if (state.entries.size >= 3) {
                        Podium(state.entries.take(3))
                    }
                    state.entries.drop(3).forEachIndexed { index, entry ->
                        LeaderboardRow(rank = index + 4, entry = entry)
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))
        }
    }
}

@Composable
private fun Podium(entries: List<LeaderboardEntry>) {
    val first = entries.getOrNull(0)
    val second = entries.getOrNull(1)
    val third = entries.getOrNull(2)
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        if (second != null) PodiumPlace(2, second, TuneTriviaPalette.Muted)
        if (first != null) PodiumPlace(1, first, TuneTriviaPalette.Highlight)
        if (third != null) PodiumPlace(3, third, TuneTriviaPalette.Tertiary)
    }
}

@Composable
private fun PodiumPlace(rank: Int, entry: LeaderboardEntry, color: androidx.compose.ui.graphics.Color) {
    TuneTriviaCard {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(text = "#$rank", color = color, fontWeight = FontWeight.Bold)
            Text(text = entry.displayName, color = TuneTriviaPalette.Text)
            Text(text = "${entry.totalScore} pts", color = color, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun LeaderboardRow(rank: Int, entry: LeaderboardEntry) {
    TuneTriviaCard {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    text = "#$rank ${entry.displayName}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TuneTriviaPalette.Text,
                )
                Text(
                    text = "${entry.totalGames} games · ${entry.totalCorrectTrivia} trivia",
                    style = MaterialTheme.typography.bodySmall,
                    color = TuneTriviaPalette.Muted,
                )
            }
            Text(
                text = "${entry.totalScore} pts",
                style = MaterialTheme.typography.bodyMedium,
                color = TuneTriviaPalette.Accent,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

