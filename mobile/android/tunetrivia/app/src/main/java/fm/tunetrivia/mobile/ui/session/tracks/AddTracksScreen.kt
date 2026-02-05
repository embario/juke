package fm.tunetrivia.mobile.ui.session.tracks

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
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.foundation.text.KeyboardOptions
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
import fm.tunetrivia.mobile.model.SpotifyTrack

@Composable
fun AddTracksScreen(
    sessionId: Int,
    remainingSlots: Int,
    onBack: () -> Unit,
    viewModel: AddTracksViewModel = viewModel(),
) {
    val state by viewModel.uiState
    val isMutatingTracks = state.isAddingTrack || state.isAutoSelecting

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
            TextButton(
                onClick = onBack,
                contentPadding = PaddingValues(0.dp),
                enabled = !isMutatingTracks,
            ) {
                Text(text = "Back", color = TuneTriviaPalette.Secondary)
            }

            Text(
                text = "Add Tracks",
                style = MaterialTheme.typography.headlineLarge,
                color = TuneTriviaPalette.Text,
            )

            TuneTriviaInputField(
                label = "Search",
                value = state.query,
                onValueChange = viewModel::updateQuery,
                placeholder = "Search for songs...",
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { viewModel.search() }),
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    text = "$remainingSlots slots remaining",
                    style = MaterialTheme.typography.bodySmall,
                    color = TuneTriviaPalette.Muted,
                )
                TuneTriviaButton(
                    onClick = { viewModel.autoFill(sessionId, remainingSlots, onBack) },
                    variant = TuneTriviaButtonVariant.LINK,
                    fillMaxWidth = false,
                    enabled = remainingSlots > 0 && !state.isAutoSelecting && !state.isAddingTrack,
                ) {
                    Text(text = if (state.isAutoSelecting) "Auto-filling..." else "Auto-fill")
                }
            }

            TuneTriviaButton(
                onClick = { viewModel.search() },
                variant = TuneTriviaButtonVariant.SECONDARY,
                enabled = state.query.isNotBlank() && !state.isSearching && !isMutatingTracks,
            ) {
                Text(text = if (state.isSearching) "Searching..." else "Search")
            }

            if (state.error != null) {
                TuneTriviaStatusBanner(message = state.error, variant = TuneTriviaStatusVariant.ERROR)
            }
            if (state.success != null) {
                TuneTriviaStatusBanner(message = state.success, variant = TuneTriviaStatusVariant.SUCCESS)
            }

            if (state.isSearching) {
                TuneTriviaSpinner()
            } else if (state.results.isEmpty() && state.query.isNotBlank()) {
                TuneTriviaCard {
                    Text(
                        text = "No results found",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TuneTriviaPalette.Muted,
                    )
                }
            } else if (state.results.isEmpty()) {
                TuneTriviaCard {
                    Text(
                        text = "Search for songs to add",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TuneTriviaPalette.Muted,
                    )
                }
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    state.results.forEach { track ->
                        TrackResultRow(
                            track = track,
                            onAdd = { viewModel.addTrack(sessionId, track) },
                            isAdding = state.addingTrackId == track.id,
                            addEnabled = !isMutatingTracks,
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))
        }
    }
}

@Composable
private fun TrackResultRow(
    track: SpotifyTrack,
    onAdd: () -> Unit,
    isAdding: Boolean,
    addEnabled: Boolean,
) {
    TuneTriviaCard {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    text = track.name,
                    style = MaterialTheme.typography.bodyMedium,
                    color = TuneTriviaPalette.Text,
                )
                Text(
                    text = track.artistName,
                    style = MaterialTheme.typography.bodySmall,
                    color = TuneTriviaPalette.Muted,
                )
            }
            TuneTriviaButton(
                onClick = onAdd,
                variant = TuneTriviaButtonVariant.LINK,
                fillMaxWidth = false,
                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 6.dp),
                enabled = addEnabled && !isAdding,
            ) {
                Text(text = if (isAdding) "Adding..." else "Add")
            }
        }
    }
}
