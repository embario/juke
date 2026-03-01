package fm.shotclock.mobile.ui.session.lobby

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import fm.shotclock.mobile.core.design.ShotClockPalette
import fm.shotclock.mobile.core.design.components.SCButtonVariant
import fm.shotclock.mobile.core.design.components.SCStatusVariant
import fm.shotclock.mobile.core.design.components.ShotClockButton
import fm.shotclock.mobile.core.design.components.ShotClockCard
import fm.shotclock.mobile.core.design.components.ShotClockChip
import fm.shotclock.mobile.core.design.components.ShotClockSpinner
import fm.shotclock.mobile.core.design.components.ShotClockStatusBanner
import fm.shotclock.mobile.model.PowerHourSession
import fm.shotclock.mobile.model.SessionPlayer
import fm.shotclock.mobile.model.SessionStatus
import fm.shotclock.mobile.model.SessionTrack
import fm.shotclock.mobile.ui.session.share.shareInvite

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun SessionLobbyScreen(
    viewModel: SessionLobbyViewModel,
    onNavigateBack: () -> Unit,
    onNavigateToAddTracks: () -> Unit,
    onNavigateToPlayback: () -> Unit,
    onNavigateToEnded: () -> Unit,
) {
    val state = viewModel.uiState
    val session = state.session
    val context = LocalContext.current

    // Navigate based on session status
    if (session != null) {
        when (session.status) {
            SessionStatus.ACTIVE, SessionStatus.PAUSED -> {
                onNavigateToPlayback()
                return
            }
            SessionStatus.ENDED -> {
                onNavigateToEnded()
                return
            }
            SessionStatus.LOBBY -> { /* Stay on this screen */ }
        }
    }

    // Delete confirmation dialog
    if (state.showDeleteConfirm) {
        AlertDialog(
            onDismissRequest = viewModel::dismissDeleteConfirmation,
            title = {
                Text(
                    text = "Delete Session",
                    color = ShotClockPalette.Text,
                )
            },
            text = {
                Text(
                    text = "Are you sure you want to delete this session? This action cannot be undone.",
                    color = ShotClockPalette.Muted,
                )
            },
            confirmButton = {
                TextButton(onClick = { viewModel.deleteSession(onNavigateBack) }) {
                    Text(
                        text = "Delete",
                        color = ShotClockPalette.Error,
                    )
                }
            },
            dismissButton = {
                TextButton(onClick = viewModel::dismissDeleteConfirmation) {
                    Text(
                        text = "Cancel",
                        color = ShotClockPalette.Text,
                    )
                }
            },
            containerColor = ShotClockPalette.Panel,
        )
    }

    Scaffold(
        containerColor = Color.Transparent,
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = session?.title ?: "Session Lobby",
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
                actions = {
                    if (session != null) {
                        IconButton(onClick = {
                            shareInvite(context, session.inviteCode, session.title)
                        }) {
                            Icon(
                                imageVector = Icons.Default.Share,
                                contentDescription = "Share",
                                tint = ShotClockPalette.Accent,
                            )
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Color.Transparent,
                ),
            )
        },
    ) { paddingValues ->
        when {
            state.isLoading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues),
                    contentAlignment = Alignment.Center,
                ) {
                    ShotClockSpinner()
                }
            }
            state.error != null && session == null -> {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues)
                        .padding(24.dp),
                    verticalArrangement = Arrangement.Center,
                ) {
                    ShotClockStatusBanner(
                        message = state.error,
                        variant = SCStatusVariant.ERROR,
                    )
                }
            }
            session != null -> {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues)
                        .verticalScroll(rememberScrollState())
                        .padding(horizontal = 24.dp),
                ) {
                    // Error banner (non-fatal)
                    ShotClockStatusBanner(
                        message = state.error,
                        variant = SCStatusVariant.ERROR,
                    )
                    if (state.error != null) Spacer(modifier = Modifier.height(16.dp))

                    // Invite code card
                    ShotClockCard(
                        borderColor = ShotClockPalette.Accent.copy(alpha = 0.3f),
                    ) {
                        Text(
                            text = "INVITE CODE",
                            style = MaterialTheme.typography.labelLarge,
                            color = ShotClockPalette.Muted,
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = session.inviteCode,
                            style = MaterialTheme.typography.displayLarge.copy(
                                fontFamily = FontFamily.Monospace,
                                letterSpacing = 6.sp,
                            ),
                            color = ShotClockPalette.Accent,
                            textAlign = TextAlign.Center,
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    copyToClipboard(context, session.inviteCode)
                                },
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Tap to copy",
                            style = MaterialTheme.typography.bodySmall,
                            color = ShotClockPalette.Muted,
                            textAlign = TextAlign.Center,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    // Config badges
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        ShotClockChip(
                            label = "${session.tracksPerPlayer} tracks/player",
                            selected = false,
                            accentColor = ShotClockPalette.Secondary,
                            onClick = {},
                        )
                        ShotClockChip(
                            label = "${session.maxTracks} max tracks",
                            selected = false,
                            accentColor = ShotClockPalette.Secondary,
                            onClick = {},
                        )
                        ShotClockChip(
                            label = "${session.secondsPerTrack}s per track",
                            selected = false,
                            accentColor = ShotClockPalette.Secondary,
                            onClick = {},
                        )
                    }

                    Spacer(modifier = Modifier.height(24.dp))

                    // Players section
                    SectionLabel(title = "Players (${state.players.size})")
                    Spacer(modifier = Modifier.height(8.dp))
                    ShotClockCard {
                        if (state.players.isEmpty()) {
                            Text(
                                text = "No players yet",
                                style = MaterialTheme.typography.bodyMedium,
                                color = ShotClockPalette.Muted,
                            )
                        } else {
                            state.players.forEachIndexed { index, player ->
                                PlayerRow(player = player)
                                if (index < state.players.lastIndex) {
                                    Spacer(modifier = Modifier.height(12.dp))
                                }
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(24.dp))

                    // Tracks section
                    SectionLabel(title = "Tracks (${state.tracks.size})")
                    Spacer(modifier = Modifier.height(8.dp))
                    ShotClockCard {
                        if (state.tracks.isEmpty()) {
                            Text(
                                text = "No tracks added yet",
                                style = MaterialTheme.typography.bodyMedium,
                                color = ShotClockPalette.Muted,
                            )
                        } else {
                            state.tracks.forEachIndexed { index, track ->
                                TrackRow(index = index + 1, track = track)
                                if (index < state.tracks.lastIndex) {
                                    Spacer(modifier = Modifier.height(12.dp))
                                }
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(24.dp))

                    // Add Tracks button
                    ShotClockButton(
                        onClick = onNavigateToAddTracks,
                        modifier = Modifier.fillMaxWidth(),
                        variant = SCButtonVariant.SECONDARY,
                    ) {
                        Text(text = "Add Tracks")
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    // Start button (admin only)
                    if (viewModel.isAdmin) {
                        if (state.isStarting) {
                            Box(
                                modifier = Modifier.fillMaxWidth(),
                                contentAlignment = Alignment.Center,
                            ) {
                                ShotClockSpinner()
                            }
                        } else {
                            ShotClockButton(
                                onClick = { viewModel.startSession(onNavigateToPlayback) },
                                modifier = Modifier.fillMaxWidth(),
                                variant = SCButtonVariant.PRIMARY,
                                enabled = state.tracks.isNotEmpty(),
                            ) {
                                Text(text = "Start Session")
                            }
                        }

                        Spacer(modifier = Modifier.height(12.dp))

                        // Delete session button
                        if (state.isDeleting) {
                            Box(
                                modifier = Modifier.fillMaxWidth(),
                                contentAlignment = Alignment.Center,
                            ) {
                                ShotClockSpinner()
                            }
                        } else {
                            ShotClockButton(
                                onClick = viewModel::showDeleteConfirmation,
                                modifier = Modifier.fillMaxWidth(),
                                variant = SCButtonVariant.DESTRUCTIVE,
                            ) {
                                Text(text = "Delete Session")
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(32.dp))
                }
            }
        }
    }
}

@Composable
private fun SectionLabel(title: String) {
    Text(
        text = title.uppercase(),
        style = MaterialTheme.typography.labelLarge,
        color = ShotClockPalette.Muted,
        modifier = Modifier.padding(start = 4.dp),
    )
}

@Composable
private fun PlayerRow(player: SessionPlayer) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (player.isAdmin) {
            Text(
                text = "\uD83D\uDC51",
                fontSize = 16.sp,
            )
            Spacer(modifier = Modifier.width(8.dp))
        }
        Text(
            text = player.displayName,
            style = MaterialTheme.typography.bodyMedium.copy(
                fontWeight = if (player.isAdmin) FontWeight.SemiBold else FontWeight.Normal,
            ),
            color = ShotClockPalette.Text,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun TrackRow(index: Int, track: SessionTrack) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // Track number
        Box(
            modifier = Modifier
                .size(28.dp)
                .clip(CircleShape)
                .background(ShotClockPalette.PanelAlt),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = "$index",
                style = MaterialTheme.typography.labelLarge,
                color = ShotClockPalette.Muted,
            )
        }
        Spacer(modifier = Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = track.trackName,
                style = MaterialTheme.typography.bodyMedium,
                color = ShotClockPalette.Text,
                maxLines = 1,
            )
            Row {
                Text(
                    text = track.trackArtist,
                    style = MaterialTheme.typography.bodySmall,
                    color = ShotClockPalette.Muted,
                    maxLines = 1,
                )
                if (track.addedByUsername.isNotBlank()) {
                    Text(
                        text = " \u00B7 ${track.addedByUsername}",
                        style = MaterialTheme.typography.bodySmall,
                        color = ShotClockPalette.Muted.copy(alpha = 0.6f),
                        maxLines = 1,
                    )
                }
            }
        }
    }
}

private fun copyToClipboard(context: Context, text: String) {
    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    clipboard.setPrimaryClip(ClipData.newPlainText("Invite Code", text))
    Toast.makeText(context, "Invite code copied!", Toast.LENGTH_SHORT).show()
}
