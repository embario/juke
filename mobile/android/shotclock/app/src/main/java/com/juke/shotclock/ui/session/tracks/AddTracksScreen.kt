package com.juke.shotclock.ui.session.tracks

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.TabRowDefaults
import androidx.compose.material3.TabRowDefaults.tabIndicatorOffset
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.juke.shotclock.core.design.ShotClockPalette
import com.juke.shotclock.core.design.components.SCStatusVariant
import com.juke.shotclock.core.design.components.ShotClockCard
import com.juke.shotclock.core.design.components.ShotClockSpinner
import com.juke.shotclock.core.design.components.ShotClockStatusBanner
import com.juke.shotclock.model.PowerHourSession
import com.juke.shotclock.model.Track

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddTracksScreen(
    viewModel: AddTracksViewModel,
    onNavigateBack: () -> Unit,
) {
    val state = viewModel.uiState

    Scaffold(
        containerColor = Color.Transparent,
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = "Add Tracks",
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
                .padding(paddingValues),
        ) {
            // Error banner
            if (state.error != null) {
                ShotClockStatusBanner(
                    message = state.error,
                    variant = SCStatusVariant.ERROR,
                    modifier = Modifier.padding(horizontal = 24.dp),
                )
                Spacer(modifier = Modifier.height(8.dp))
            }

            // Tab row
            TabRow(
                selectedTabIndex = if (state.activeTab == AddTracksTab.SEARCH) 0 else 1,
                containerColor = Color.Transparent,
                contentColor = ShotClockPalette.Accent,
                indicator = { tabPositions ->
                    val selectedIndex = if (state.activeTab == AddTracksTab.SEARCH) 0 else 1
                    TabRowDefaults.SecondaryIndicator(
                        modifier = Modifier.tabIndicatorOffset(tabPositions[selectedIndex]),
                        color = ShotClockPalette.Accent,
                    )
                },
            ) {
                Tab(
                    selected = state.activeTab == AddTracksTab.SEARCH,
                    onClick = { viewModel.switchTab(AddTracksTab.SEARCH) },
                    text = {
                        Text(
                            text = "Search",
                            color = if (state.activeTab == AddTracksTab.SEARCH) {
                                ShotClockPalette.Accent
                            } else {
                                ShotClockPalette.Muted
                            },
                        )
                    },
                )
                Tab(
                    selected = state.activeTab == AddTracksTab.IMPORT,
                    onClick = { viewModel.switchTab(AddTracksTab.IMPORT) },
                    text = {
                        Text(
                            text = "Import",
                            color = if (state.activeTab == AddTracksTab.IMPORT) {
                                ShotClockPalette.Accent
                            } else {
                                ShotClockPalette.Muted
                            },
                        )
                    },
                )
            }

            when (state.activeTab) {
                AddTracksTab.SEARCH -> SearchTab(
                    query = state.query,
                    onQueryChange = viewModel::updateQuery,
                    isSearching = state.isSearching,
                    results = state.searchResults,
                    sessionTrackIds = state.sessionTrackIds,
                    onAddTrack = viewModel::addTrack,
                    onRemoveTrack = viewModel::removeTrack,
                )
                AddTracksTab.IMPORT -> ImportTab(
                    isLoading = state.isLoadingSessions,
                    sessions = state.previousSessions,
                    isImporting = state.isImporting,
                    onImport = viewModel::importFromSession,
                )
            }
        }
    }
}

@Composable
private fun SearchTab(
    query: String,
    onQueryChange: (String) -> Unit,
    isSearching: Boolean,
    results: List<Track>,
    sessionTrackIds: Set<Int>,
    onAddTrack: (Track) -> Unit,
    onRemoveTrack: (Track) -> Unit,
) {
    Column(modifier = Modifier.fillMaxSize()) {
        // Search bar
        val shape = RoundedCornerShape(14.dp)
        TextField(
            value = query,
            onValueChange = onQueryChange,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp, vertical = 12.dp)
                .border(
                    width = 1.dp,
                    color = ShotClockPalette.Border,
                    shape = shape,
                )
                .background(ShotClockPalette.PanelAlt.copy(alpha = 0.65f), shape),
            textStyle = MaterialTheme.typography.bodyLarge,
            placeholder = {
                Text(
                    text = "Search tracks...",
                    color = ShotClockPalette.Muted,
                )
            },
            leadingIcon = {
                Icon(
                    imageVector = Icons.Default.Search,
                    contentDescription = "Search",
                    tint = ShotClockPalette.Muted,
                )
            },
            singleLine = true,
            shape = shape,
            colors = TextFieldDefaults.colors(
                focusedTextColor = ShotClockPalette.Text,
                unfocusedTextColor = ShotClockPalette.Text,
                focusedContainerColor = Color.Transparent,
                unfocusedContainerColor = Color.Transparent,
                cursorColor = ShotClockPalette.Accent,
                focusedIndicatorColor = Color.Transparent,
                unfocusedIndicatorColor = Color.Transparent,
            ),
        )

        when {
            isSearching -> {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 32.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    ShotClockSpinner()
                }
            }
            results.isEmpty() && query.isNotBlank() -> {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 32.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = "No tracks found.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = ShotClockPalette.Muted,
                    )
                }
            }
            results.isEmpty() -> {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 32.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = "Search for tracks to add to your session.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = ShotClockPalette.Muted,
                    )
                }
            }
            else -> {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(
                        horizontal = 24.dp,
                        vertical = 8.dp,
                    ),
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    items(results, key = { it.id }) { track ->
                        val isInSession = sessionTrackIds.contains(track.id)
                        TrackSearchRow(
                            track = track,
                            isInSession = isInSession,
                            onToggle = {
                                if (isInSession) onRemoveTrack(track) else onAddTrack(track)
                            },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun TrackSearchRow(
    track: Track,
    isInSession: Boolean,
    onToggle: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .clickable(onClick = onToggle)
            .padding(vertical = 10.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = track.name,
                    style = MaterialTheme.typography.bodyMedium,
                    color = ShotClockPalette.Text,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = false),
                )
                if (track.explicit) {
                    Spacer(modifier = Modifier.width(6.dp))
                    Box(
                        modifier = Modifier
                            .background(
                                ShotClockPalette.Muted.copy(alpha = 0.3f),
                                RoundedCornerShape(3.dp),
                            )
                            .padding(horizontal = 4.dp, vertical = 1.dp),
                    ) {
                        Text(
                            text = "E",
                            style = MaterialTheme.typography.labelSmall.copy(
                                fontWeight = FontWeight.Bold,
                            ),
                            color = ShotClockPalette.Muted,
                        )
                    }
                }
            }
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = buildString {
                    append(track.artistName)
                    if (track.albumName.isNotBlank()) {
                        append(" \u00B7 ")
                        append(track.albumName)
                    }
                },
                style = MaterialTheme.typography.bodySmall,
                color = ShotClockPalette.Muted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (track.durationMs > 0) {
                val minutes = track.durationMs / 60_000
                val seconds = (track.durationMs % 60_000) / 1000
                Text(
                    text = "$minutes:%02d".format(seconds),
                    style = MaterialTheme.typography.labelMedium,
                    color = ShotClockPalette.Muted.copy(alpha = 0.6f),
                )
            }
        }

        Spacer(modifier = Modifier.width(12.dp))

        Box(
            modifier = Modifier
                .size(36.dp)
                .clip(CircleShape)
                .background(
                    if (isInSession) ShotClockPalette.Success.copy(alpha = 0.2f)
                    else ShotClockPalette.Accent.copy(alpha = 0.15f),
                )
                .clickable(onClick = onToggle),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = if (isInSession) Icons.Default.Check else Icons.Default.Add,
                contentDescription = if (isInSession) "Added" else "Add",
                tint = if (isInSession) ShotClockPalette.Success else ShotClockPalette.Accent,
                modifier = Modifier.size(20.dp),
            )
        }
    }
}

@Composable
private fun ImportTab(
    isLoading: Boolean,
    sessions: List<PowerHourSession>,
    isImporting: Boolean,
    onImport: (String) -> Unit,
) {
    when {
        isLoading || isImporting -> {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(top = 32.dp),
                contentAlignment = Alignment.TopCenter,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    ShotClockSpinner()
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        text = if (isImporting) "Importing tracks..." else "Loading sessions...",
                        style = MaterialTheme.typography.bodyMedium,
                        color = ShotClockPalette.Muted,
                    )
                }
            }
        }
        sessions.isEmpty() -> {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(top = 32.dp),
                contentAlignment = Alignment.TopCenter,
            ) {
                Text(
                    text = "No previous sessions with tracks.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = ShotClockPalette.Muted,
                )
            }
        }
        else -> {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(
                    horizontal = 24.dp,
                    vertical = 12.dp,
                ),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(sessions, key = { it.id }) { session ->
                    ShotClockCard(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onImport(session.id) },
                    ) {
                        Text(
                            text = session.title,
                            style = MaterialTheme.typography.titleLarge,
                            color = ShotClockPalette.Text,
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "${session.trackCount} tracks \u00B7 ${session.playerCount} players",
                            style = MaterialTheme.typography.bodySmall,
                            color = ShotClockPalette.Muted,
                        )
                    }
                }
            }
        }
    }
}
