package com.juke.shotclock.ui.session.create

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.juke.shotclock.core.design.ShotClockPalette
import com.juke.shotclock.core.design.components.SCButtonVariant
import com.juke.shotclock.core.design.components.SCStatusVariant
import com.juke.shotclock.core.design.components.ShotClockButton
import com.juke.shotclock.core.design.components.ShotClockCard
import com.juke.shotclock.core.design.components.ShotClockChip
import com.juke.shotclock.core.design.components.ShotClockInputField
import com.juke.shotclock.core.design.components.ShotClockSpinner
import com.juke.shotclock.core.design.components.ShotClockStatusBanner
import com.juke.shotclock.model.PowerHourSession

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun CreateSessionScreen(
    onNavigateBack: () -> Unit,
    onSessionCreated: (PowerHourSession) -> Unit,
    viewModel: CreateSessionViewModel = viewModel(),
) {
    val state = viewModel.uiState

    val transitionSounds = listOf("airhorn", "buzzer", "bell", "whistle", "glass_clink")

    Scaffold(
        containerColor = Color.Transparent,
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = "New Session",
                        color = ShotClockPalette.Text,
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back",
                            tint = ShotClockPalette.Accent,
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Color.Transparent,
                ),
            )
        },
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp),
        ) {
            // Error banner
            ShotClockStatusBanner(
                message = state.error,
                variant = SCStatusVariant.ERROR,
            )
            if (state.error != null) Spacer(modifier = Modifier.height(16.dp))

            // Title
            ShotClockInputField(
                label = "Session Title",
                value = state.title,
                onValueChange = viewModel::updateTitle,
                placeholder = "Friday Night Power Hour",
            )

            Spacer(modifier = Modifier.height(24.dp))

            // Settings card
            ShotClockCard {
                // Tracks per player
                SliderSetting(
                    label = "Tracks per Player",
                    value = state.tracksPerPlayer.toFloat(),
                    valueLabel = "${state.tracksPerPlayer}",
                    range = 1f..10f,
                    steps = 8,
                    onValueChange = { viewModel.updateTracksPerPlayer(it.toInt()) },
                )

                Spacer(modifier = Modifier.height(20.dp))

                // Max tracks
                SliderSetting(
                    label = "Max Tracks",
                    value = state.maxTracks.toFloat(),
                    valueLabel = "${state.maxTracks}",
                    range = 10f..60f,
                    steps = 9,
                    onValueChange = { viewModel.updateMaxTracks(it.toInt()) },
                )

                Spacer(modifier = Modifier.height(20.dp))

                // Seconds per track
                SliderSetting(
                    label = "Seconds per Track",
                    value = state.secondsPerTrack.toFloat(),
                    valueLabel = "${state.secondsPerTrack}s",
                    range = 30f..120f,
                    steps = 8,
                    onValueChange = { viewModel.updateSecondsPerTrack(it.toInt()) },
                )
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Transition sound
            Text(
                text = "TRANSITION SOUND",
                style = MaterialTheme.typography.labelLarge,
                color = ShotClockPalette.Muted,
                modifier = Modifier.padding(start = 4.dp, bottom = 8.dp),
            )
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                transitionSounds.forEach { sound ->
                    ShotClockChip(
                        label = sound.replace("_", " ").replaceFirstChar { it.uppercase() },
                        selected = state.transitionClip == sound,
                        onClick = { viewModel.updateTransitionClip(sound) },
                    )
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Trivia mode toggle
            ShotClockCard {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Trivia Mode",
                            style = MaterialTheme.typography.titleLarge,
                            color = ShotClockPalette.Text,
                        )
                        Spacer(modifier = Modifier.height(2.dp))
                        Text(
                            text = "Hide who added each track",
                            style = MaterialTheme.typography.bodySmall,
                            color = ShotClockPalette.Muted,
                        )
                    }
                    Spacer(modifier = Modifier.width(16.dp))
                    Switch(
                        checked = state.hideTrackOwners,
                        onCheckedChange = { viewModel.toggleHideTrackOwners() },
                        colors = SwitchDefaults.colors(
                            checkedThumbColor = ShotClockPalette.Text,
                            checkedTrackColor = ShotClockPalette.Accent,
                            uncheckedThumbColor = ShotClockPalette.Muted,
                            uncheckedTrackColor = ShotClockPalette.PanelAlt,
                            uncheckedBorderColor = ShotClockPalette.Border,
                        ),
                    )
                }
            }

            Spacer(modifier = Modifier.height(32.dp))

            // Create button
            if (state.isLoading) {
                Box(
                    modifier = Modifier.fillMaxWidth(),
                    contentAlignment = Alignment.Center,
                ) {
                    ShotClockSpinner()
                }
            } else {
                ShotClockButton(
                    onClick = { viewModel.createSession(onSessionCreated) },
                    modifier = Modifier.fillMaxWidth(),
                    variant = SCButtonVariant.PRIMARY,
                    enabled = state.title.isNotBlank(),
                ) {
                    Text(text = "Create Session")
                }
            }

            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

@Composable
private fun SliderSetting(
    label: String,
    value: Float,
    valueLabel: String,
    range: ClosedFloatingPointRange<Float>,
    steps: Int,
    onValueChange: (Float) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodyMedium,
            color = ShotClockPalette.Text,
        )
        Text(
            text = valueLabel,
            style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold),
            color = ShotClockPalette.Accent,
        )
    }
    Spacer(modifier = Modifier.height(4.dp))
    Slider(
        value = value,
        onValueChange = onValueChange,
        valueRange = range,
        steps = steps,
        modifier = Modifier.fillMaxWidth(),
        colors = SliderDefaults.colors(
            thumbColor = ShotClockPalette.Accent,
            activeTrackColor = ShotClockPalette.Accent,
            inactiveTrackColor = ShotClockPalette.PanelAlt,
            activeTickColor = ShotClockPalette.AccentSoft,
            inactiveTickColor = ShotClockPalette.Muted.copy(alpha = 0.3f),
        ),
    )
}
