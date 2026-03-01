package fm.shotclock.mobile.ui.session.playback

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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import fm.shotclock.mobile.core.design.ShotClockPalette
import fm.shotclock.mobile.core.design.components.CountdownRing
import fm.shotclock.mobile.core.design.components.SCButtonVariant
import fm.shotclock.mobile.core.design.components.SCStatusVariant
import fm.shotclock.mobile.core.design.components.ShotClockButton
import fm.shotclock.mobile.core.design.components.ShotClockSpinner
import fm.shotclock.mobile.core.design.components.ShotClockStatusBanner
import fm.shotclock.mobile.model.SessionStatus
import fm.shotclock.mobile.model.SessionTrack
import fm.shotclock.mobile.ui.session.share.sharePlaylist

@Composable
fun PlaybackScreen(
    viewModel: PlaybackViewModel,
    onNavigateToEnded: () -> Unit,
) {
    val state = viewModel.uiState
    val session = state.session
    val context = LocalContext.current

    when {
        state.isLoading -> {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center,
            ) {
                ShotClockSpinner()
            }
        }
        state.hasEnded -> {
            CompletionOverlay(
                tracks = state.tracks,
                onDone = onNavigateToEnded,
                onSharePlaylist = { sharePlaylist(context, state.tracks, session?.title.orEmpty()) },
            )
        }
        session != null -> {
            ActivePlayback(
                viewModel = viewModel,
                state = state,
            )
        }
        state.error != null -> {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(24.dp),
                verticalArrangement = Arrangement.Center,
            ) {
                ShotClockStatusBanner(
                    message = state.error,
                    variant = SCStatusVariant.ERROR,
                )
            }
        }
    }
}

@Composable
private fun ActivePlayback(
    viewModel: PlaybackViewModel,
    state: PlaybackUiState,
) {
    val session = state.session ?: return
    val currentTrack = viewModel.currentTrack
    val isPaused = session.status == SessionStatus.PAUSED

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp, vertical = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // Error banner
        ShotClockStatusBanner(
            message = state.error,
            variant = SCStatusVariant.ERROR,
        )
        if (state.error != null) Spacer(modifier = Modifier.height(16.dp))

        // Track progress
        Text(
            text = viewModel.trackProgress,
            style = MaterialTheme.typography.labelLarge,
            color = ShotClockPalette.Muted,
        )

        Spacer(modifier = Modifier.height(32.dp))

        // Countdown ring
        val totalSeconds = session.secondsPerTrack
        val progress = if (totalSeconds > 0) {
            state.secondsRemaining.toFloat() / totalSeconds.toFloat()
        } else 0f

        Box(contentAlignment = Alignment.Center) {
            CountdownRing(
                progress = progress,
                size = 220.dp,
                lineWidth = 16.dp,
            )
            Text(
                text = "${state.secondsRemaining}",
                style = MaterialTheme.typography.displayLarge.copy(
                    fontSize = 56.sp,
                    fontWeight = FontWeight.Bold,
                ),
                color = ShotClockPalette.Text,
            )
        }

        Spacer(modifier = Modifier.height(32.dp))

        // Current track info
        if (currentTrack != null) {
            Text(
                text = currentTrack.trackName,
                style = MaterialTheme.typography.headlineSmall.copy(
                    fontWeight = FontWeight.Bold,
                ),
                color = ShotClockPalette.Text,
                textAlign = TextAlign.Center,
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = currentTrack.trackArtist,
                style = MaterialTheme.typography.titleMedium,
                color = ShotClockPalette.Muted,
                textAlign = TextAlign.Center,
            )
        }

        if (isPaused) {
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = "PAUSED",
                style = MaterialTheme.typography.labelLarge,
                color = ShotClockPalette.Warning,
            )
        }

        Spacer(modifier = Modifier.height(48.dp))

        // Playback controls (admin only)
        if (viewModel.isAdmin) {
            Row(
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // End button
                ControlButton(
                    size = 56.dp,
                    backgroundColor = ShotClockPalette.Error.copy(alpha = 0.2f),
                    contentColor = ShotClockPalette.Error,
                    onClick = viewModel::endSession,
                    enabled = !state.isEnding,
                ) {
                    Icon(
                        imageVector = Icons.Default.Close,
                        contentDescription = "End Session",
                        modifier = Modifier.size(28.dp),
                    )
                }

                Spacer(modifier = Modifier.width(24.dp))

                // Pause / Resume button
                ControlButton(
                    size = 64.dp,
                    backgroundColor = ShotClockPalette.Accent,
                    contentColor = Color.White,
                    onClick = viewModel::pauseOrResume,
                    enabled = !state.isPausing,
                ) {
                    Icon(
                        imageVector = if (isPaused) Icons.Default.PlayArrow else Icons.Default.Pause,
                        contentDescription = if (isPaused) "Resume" else "Pause",
                        modifier = Modifier.size(32.dp),
                    )
                }

                Spacer(modifier = Modifier.width(24.dp))

                // Skip button
                ControlButton(
                    size = 56.dp,
                    backgroundColor = ShotClockPalette.Secondary.copy(alpha = 0.2f),
                    contentColor = ShotClockPalette.Secondary,
                    onClick = viewModel::skipTrack,
                    enabled = !state.isSkipping,
                ) {
                    Icon(
                        imageVector = Icons.Default.SkipNext,
                        contentDescription = "Skip",
                        modifier = Modifier.size(28.dp),
                    )
                }
            }
        } else {
            Text(
                text = "Waiting for the host to control playback...",
                style = MaterialTheme.typography.bodyMedium,
                color = ShotClockPalette.Muted,
                textAlign = TextAlign.Center,
            )
        }

        Spacer(modifier = Modifier.height(32.dp))
    }
}

@Composable
private fun ControlButton(
    size: androidx.compose.ui.unit.Dp,
    backgroundColor: Color,
    contentColor: Color,
    onClick: () -> Unit,
    enabled: Boolean = true,
    content: @Composable () -> Unit,
) {
    Surface(
        onClick = onClick,
        enabled = enabled,
        shape = CircleShape,
        color = backgroundColor,
        contentColor = contentColor,
        modifier = Modifier.size(size),
    ) {
        Box(contentAlignment = Alignment.Center) {
            content()
        }
    }
}

@Composable
private fun CompletionOverlay(
    tracks: List<SessionTrack>,
    onDone: () -> Unit,
    onSharePlaylist: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 24.dp, vertical = 32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        // Checkmark icon
        Surface(
            shape = CircleShape,
            color = ShotClockPalette.Success.copy(alpha = 0.2f),
            contentColor = ShotClockPalette.Success,
            modifier = Modifier.size(80.dp),
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(
                    imageVector = Icons.Default.Check,
                    contentDescription = "Complete",
                    modifier = Modifier.size(44.dp),
                )
            }
        }

        Spacer(modifier = Modifier.height(24.dp))

        Text(
            text = "Power Hour Complete!",
            style = MaterialTheme.typography.headlineLarge,
            color = ShotClockPalette.Text,
            textAlign = TextAlign.Center,
        )

        Spacer(modifier = Modifier.height(8.dp))

        Text(
            text = "${tracks.size} tracks played",
            style = MaterialTheme.typography.bodyMedium,
            color = ShotClockPalette.Muted,
            textAlign = TextAlign.Center,
        )

        Spacer(modifier = Modifier.height(32.dp))

        ShotClockButton(
            onClick = onSharePlaylist,
            modifier = Modifier.fillMaxWidth(),
            variant = SCButtonVariant.SECONDARY,
        ) {
            Text(text = "Share Playlist")
        }

        Spacer(modifier = Modifier.height(12.dp))

        ShotClockButton(
            onClick = onDone,
            modifier = Modifier.fillMaxWidth(),
            variant = SCButtonVariant.PRIMARY,
        ) {
            Text(text = "Done")
        }
    }
}
