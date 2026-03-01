package fm.juke.mobile.ui.search

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import fm.juke.mobile.core.design.JukePalette
import fm.juke.mobile.core.design.components.JukeButton
import fm.juke.mobile.core.design.components.JukeCard
import fm.juke.mobile.core.design.components.JukeChip
import fm.juke.mobile.core.design.components.JukeInputField
import fm.juke.mobile.core.design.components.JukeSpinner
import fm.juke.mobile.core.design.components.JukeStatusBanner
import fm.juke.mobile.core.design.components.JukeStatusVariant
import fm.juke.core.catalog.Album
import fm.juke.core.catalog.Artist
import fm.juke.core.catalog.CatalogResourceType
import fm.juke.core.catalog.Track

@Composable
fun CatalogRoute(viewModel: CatalogViewModel = viewModel()) {
    val state = viewModel.uiState
    CatalogScreen(
        state = state,
        onQueryChange = viewModel::updateQuery,
        onSearch = viewModel::search,
        onTabSelected = viewModel::setTab,
    )
}

@Composable
fun CatalogScreen(
    state: CatalogUiState,
    onQueryChange: (String) -> Unit,
    onSearch: () -> Unit,
    onTabSelected: (CatalogResourceType) -> Unit,
) {
    val listState = rememberLazyListState()
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 24.dp, vertical = 32.dp),
        state = listState,
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(text = "Discover on Juke", style = MaterialTheme.typography.headlineLarge)
                Text(
                    text = "Scan the entire catalog without leaving native. Filter the feeds to zero in on exactly what you need.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.72f),
                )
            }
        }
        item {
            SearchSurface(
                state = state,
                onQueryChange = onQueryChange,
                onSearch = onSearch,
                onTabSelected = onTabSelected,
            )
        }
        if (state.isLoading) {
            item {
                JukeCard {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        JukeSpinner()
                        Text(
                            text = "Cranking up the signal…",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f),
                        )
                    }
                }
            }
        }
        state.error?.takeIf { it.isNotBlank() }?.let { error ->
            item {
                JukeStatusBanner(message = error, variant = JukeStatusVariant.ERROR)
            }
        }

        val hasQuery = state.query.trim().isNotEmpty()
        val activeItems = when (state.activeTab) {
            CatalogResourceType.ARTISTS -> state.artists
            CatalogResourceType.ALBUMS -> state.albums
            CatalogResourceType.TRACKS -> state.tracks
        }
        if (!state.isLoading && hasQuery && activeItems.isEmpty()) {
            item {
                JukeCard {
                    Text(
                        text = "No matches yet",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        text = "Double-check your spelling or try widening the filters.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f),
                    )
                }
            }
        }

        when (state.activeTab) {
            CatalogResourceType.ARTISTS -> {
                if (state.artists.isNotEmpty()) {
                    item {
                        CatalogSection(title = "People", subtitle = "Artists lighting up the feed") {
                            state.artists.forEachIndexed { index, artist ->
                                CatalogResultRow(
                                    title = artist.name,
                                    subtitle = "Followers ${artist.followers} · Popularity ${artist.popularity}",
                                )
                                if (index < state.artists.lastIndex) {
                                    HorizontalDivider(color = JukePalette.Border)
                                }
                            }
                        }
                    }
                }
            }
            CatalogResourceType.ALBUMS -> {
                if (state.albums.isNotEmpty()) {
                    item {
                        CatalogSection(title = "Albums", subtitle = "Records worth a spin") {
                            state.albums.forEachIndexed { index, album ->
                                CatalogResultRow(
                                    title = album.name,
                                    subtitle = "${album.albumType.lowercase().replaceFirstChar { it.titlecase() }} · ${album.releaseDate}",
                                    meta = "${album.totalTracks} tracks",
                                )
                                if (index < state.albums.lastIndex) {
                                    HorizontalDivider(color = JukePalette.Border)
                                }
                            }
                        }
                    }
                }
            }
            CatalogResourceType.TRACKS -> {
                if (state.tracks.isNotEmpty()) {
                    item {
                        CatalogSection(title = "Tracks", subtitle = "Songs matching your query") {
                            state.tracks.forEachIndexed { index, track ->
                                CatalogResultRow(
                                    title = track.name,
                                    subtitle = "Track ${track.trackNumber} · ${formatDuration(track.durationMs)}",
                                    meta = if (track.explicit) "Explicit" else null,
                                )
                                if (index < state.tracks.lastIndex) {
                                    HorizontalDivider(color = JukePalette.Border)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SearchSurface(
    state: CatalogUiState,
    onQueryChange: (String) -> Unit,
    onSearch: () -> Unit,
    onTabSelected: (CatalogResourceType) -> Unit,
) {
    JukeCard {
        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(text = "Global Search", style = MaterialTheme.typography.titleMedium)
            Text(
                text = "Choose what you want to surface and let the signal rip across profiles, artists, albums, or tracks.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f),
            )
            JukeInputField(
                label = "Query",
                value = state.query,
                onValueChange = onQueryChange,
                placeholder = "Search profiles, artists, albums, tracks",
                keyboardOptions = KeyboardOptions.Default.copy(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { onSearch() }),
            )
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                CatalogResourceType.values().forEach { resource ->
                    JukeChip(
                        label = resource.label,
                        selected = resource == state.activeTab,
                        modifier = Modifier.weight(1f),
                        onClick = { if (resource != state.activeTab) onTabSelected(resource) },
                    )
                }
            }
            JukeButton(
                onClick = onSearch,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(54.dp),
                enabled = state.query.trim().length >= 2 && !state.isLoading,
            ) {
                Text(text = "Search")
            }
        }
    }
}

@Composable
private fun CatalogSection(
    title: String,
    subtitle: String,
    content: @Composable ColumnScope.() -> Unit,
) {
    JukeCard {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    text = title.uppercase(),
                    style = MaterialTheme.typography.labelLarge,
                    color = JukePalette.Muted,
                )
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f),
                )
            }
            content()
        }
    }
}

@Composable
private fun CatalogResultRow(
    title: String,
    subtitle: String,
    meta: String? = null,
) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            text = title,
            style = MaterialTheme.typography.titleMedium,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            text = subtitle,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.8f),
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        meta?.let {
            Text(
                text = it,
                style = MaterialTheme.typography.labelLarge,
                color = JukePalette.Accent,
            )
        }
    }
}

private fun formatDuration(durationMs: Int): String {
    if (durationMs <= 0) return "--"
    val totalSeconds = durationMs / 1000
    val minutes = totalSeconds / 60
    val seconds = totalSeconds % 60
    return "%d:%02d".format(minutes, seconds)
}
