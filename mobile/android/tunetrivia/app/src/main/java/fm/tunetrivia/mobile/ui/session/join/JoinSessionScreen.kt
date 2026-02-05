package fm.tunetrivia.mobile.ui.session.join

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import fm.tunetrivia.mobile.core.design.TuneTriviaPalette
import fm.tunetrivia.mobile.core.design.components.TuneTriviaBackground
import fm.tunetrivia.mobile.core.design.components.TuneTriviaButton
import fm.tunetrivia.mobile.core.design.components.TuneTriviaCard
import fm.tunetrivia.mobile.core.design.components.TuneTriviaInputField
import fm.tunetrivia.mobile.core.design.components.TuneTriviaSpinner
import fm.tunetrivia.mobile.core.design.components.TuneTriviaStatusBanner
import fm.tunetrivia.mobile.core.design.components.TuneTriviaStatusVariant

@Composable
fun JoinSessionScreen(
    isAuthenticated: Boolean,
    onBack: () -> Unit,
    onJoined: (Int) -> Unit,
    viewModel: JoinSessionViewModel = viewModel(),
) {
    val state by viewModel.uiState
    val needsDisplayName = !isAuthenticated

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
                    text = "Join Game",
                    style = MaterialTheme.typography.headlineLarge,
                    color = TuneTriviaPalette.Text,
                )
                Text(
                    text = "Enter the game code to join",
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
                        label = "Game Code",
                        value = state.code,
                        onValueChange = viewModel::updateCode,
                        placeholder = "ABC123",
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Ascii,
                        ),
                    )

                    if (needsDisplayName) {
                        TuneTriviaInputField(
                            label = "Your Name",
                            value = state.displayName,
                            onValueChange = viewModel::updateDisplayName,
                            placeholder = "Enter your name",
                        )
                    }
                }
            }

            if (state.isLoading) {
                TuneTriviaSpinner()
            } else {
                TuneTriviaButton(
                    onClick = { viewModel.join(onJoined, needsDisplayName) },
                    enabled = state.code.length == 6 && (!needsDisplayName || state.displayName.isNotBlank()),
                ) {
                    Text(text = "Join Game")
                }
            }

            Spacer(modifier = Modifier.height(8.dp))
        }
    }
}
