package fm.shotclock.mobile.ui.session.ended

import androidx.compose.foundation.background
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
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import fm.shotclock.mobile.core.design.ShotClockPalette
import fm.shotclock.mobile.core.design.components.SCButtonVariant
import fm.shotclock.mobile.core.design.components.ShotClockButton
import fm.shotclock.mobile.core.design.components.ShotClockCard
import fm.shotclock.mobile.core.design.components.ShotClockSpinner
import fm.shotclock.mobile.core.di.ServiceLocator
import fm.shotclock.mobile.data.repository.PowerHourRepository
import fm.shotclock.mobile.model.PowerHourSession
import fm.shotclock.mobile.model.SessionPlayer
import fm.shotclock.mobile.model.SessionTrack
import fm.shotclock.mobile.ui.session.share.sharePlaylist

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SessionEndScreen(
    sessionId: String,
    onNavigateBack: () -> Unit,
    repository: PowerHourRepository = ServiceLocator.powerHourRepository,
) {
    var session by remember { mutableStateOf<PowerHourSession?>(null) }
    var players by remember { mutableStateOf<List<SessionPlayer>>(emptyList()) }
    var tracks by remember { mutableStateOf<List<SessionTrack>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }

    val context = LocalContext.current

    LaunchedEffect(sessionId) {
        repository.getSession(sessionId)
            .onSuccess { session = it }
        repository.listPlayers(sessionId)
            .onSuccess { players = it }
        repository.listTracks(sessionId)
            .onSuccess { tracks = it }
        isLoading = false
    }

    Scaffold(
        containerColor = Color.Transparent,
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = "Session Summary",
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
        if (isLoading) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center,
            ) {
                ShotClockSpinner()
            }
            return@Scaffold
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp),
        ) {
            // Summary card
            ShotClockCard(
                borderColor = ShotClockPalette.Success.copy(alpha = 0.3f),
            ) {
                Text(
                    text = session?.title.orEmpty(),
                    style = MaterialTheme.typography.headlineMedium,
                    color = ShotClockPalette.Text,
                )
                Spacer(modifier = Modifier.height(12.dp))
                Row(
                    horizontalArrangement = Arrangement.spacedBy(24.dp),
                ) {
                    SummaryStatItem(
                        value = "${tracks.size}",
                        label = "Tracks Played",
                    )
                    val durationMinutes = session?.let { s ->
                        val totalSec = tracks.size * s.secondsPerTrack
                        totalSec / 60
                    } ?: 0
                    SummaryStatItem(
                        value = "${durationMinutes}m",
                        label = "Duration",
                    )
                    SummaryStatItem(
                        value = "${players.size}",
                        label = "Players",
                    )
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Players section
            SectionLabel(title = "Players")
            Spacer(modifier = Modifier.height(8.dp))
            ShotClockCard {
                if (players.isEmpty()) {
                    Text(
                        text = "No players",
                        style = MaterialTheme.typography.bodyMedium,
                        color = ShotClockPalette.Muted,
                    )
                } else {
                    players.forEachIndexed { index, player ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            if (player.isAdmin) {
                                Text(
                                    text = "\uD83D\uDC51",
                                    style = MaterialTheme.typography.bodyMedium,
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                            }
                            Text(
                                text = player.displayName,
                                style = MaterialTheme.typography.bodyMedium.copy(
                                    fontWeight = if (player.isAdmin) FontWeight.SemiBold else FontWeight.Normal,
                                ),
                                color = ShotClockPalette.Text,
                            )
                        }
                        if (index < players.lastIndex) {
                            Spacer(modifier = Modifier.height(10.dp))
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Tracks section
            SectionLabel(title = "Playlist (${tracks.size} tracks)")
            Spacer(modifier = Modifier.height(8.dp))
            ShotClockCard {
                if (tracks.isEmpty()) {
                    Text(
                        text = "No tracks",
                        style = MaterialTheme.typography.bodyMedium,
                        color = ShotClockPalette.Muted,
                    )
                } else {
                    tracks.forEachIndexed { index, track ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                modifier = Modifier
                                    .size(28.dp)
                                    .clip(CircleShape)
                                    .background(ShotClockPalette.PanelAlt),
                                contentAlignment = Alignment.Center,
                            ) {
                                Text(
                                    text = "${index + 1}",
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
                        if (index < tracks.lastIndex) {
                            Spacer(modifier = Modifier.height(12.dp))
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Share playlist button
            ShotClockButton(
                onClick = {
                    sharePlaylist(context, tracks, session?.title.orEmpty())
                },
                modifier = Modifier.fillMaxWidth(),
                variant = SCButtonVariant.SECONDARY,
            ) {
                Text(text = "Share Playlist")
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Back to sessions button
            ShotClockButton(
                onClick = onNavigateBack,
                modifier = Modifier.fillMaxWidth(),
                variant = SCButtonVariant.PRIMARY,
            ) {
                Text(text = "Back to Sessions")
            }

            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

@Composable
private fun SummaryStatItem(
    value: String,
    label: String,
) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = value,
            style = MaterialTheme.typography.headlineLarge,
            color = ShotClockPalette.Accent,
        )
        Text(
            text = label,
            style = MaterialTheme.typography.labelMedium,
            color = ShotClockPalette.Muted,
        )
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
