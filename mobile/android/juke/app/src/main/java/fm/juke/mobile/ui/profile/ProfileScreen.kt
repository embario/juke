package fm.juke.mobile.ui.profile

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.BorderStroke
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import fm.juke.mobile.core.design.JukePalette
import fm.juke.mobile.core.design.components.JukeButton
import fm.juke.mobile.core.design.components.JukeCard
import fm.juke.mobile.core.design.components.JukeInputField
import fm.juke.mobile.core.design.components.JukeSpinner
import fm.juke.mobile.core.design.components.JukeStatusBanner
import fm.juke.mobile.core.design.components.JukeStatusVariant
import fm.juke.mobile.model.MusicProfile
import fm.juke.mobile.model.ProfileSummary

@Composable
fun ProfileRoute(viewModel: ProfileViewModel = viewModel()) {
    val state = viewModel.uiState
    ProfileScreen(
        state = state,
        onRefresh = viewModel::refreshMyProfile,
        onQueryChange = viewModel::updateSearchQuery,
        onSearchProfiles = viewModel::runProfileSearch,
        onSelectProfile = viewModel::focusOn,
    )
}

@Composable
fun ProfileScreen(
    state: ProfileUiState,
    onRefresh: () -> Unit,
    onQueryChange: (String) -> Unit,
    onSearchProfiles: () -> Unit,
    onSelectProfile: (ProfileSummary) -> Unit,
) {
    val listState = rememberLazyListState()
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 24.dp, vertical = 32.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp),
        state = listState,
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(text = "Profiles", style = MaterialTheme.typography.headlineLarge)
                Text(
                    text = "Tap into your sonic fingerprint or scout other listeners to align with the vibe.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f),
                )
            }
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
                            text = "Syncing your profile…",
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
        state.focusedProfile?.let { profile ->
            item { ProfileHero(profile) }
        }
        item {
            SearchProfilesSection(
                query = state.searchQuery,
                results = state.searchResults,
                onQueryChange = onQueryChange,
                onSearchProfiles = onSearchProfiles,
                onSelectProfile = onSelectProfile,
            )
        }
    }
}

@Composable
private fun ProfileHero(profile: MusicProfile) {
    JukeCard {
        Column(
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = profile.displayName.ifBlank { profile.username },
                style = MaterialTheme.typography.headlineLarge,
            )
            if (profile.tagline.isNotBlank()) {
                Text(
                    text = profile.tagline,
                    style = MaterialTheme.typography.bodyLarge,
                    color = JukePalette.Accent,
                )
            }
            if (profile.location.isNotBlank()) {
                Text(
                    text = profile.location,
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f),
                )
            }
            if (profile.bio.isNotBlank()) {
                Text(text = profile.bio, style = MaterialTheme.typography.bodyMedium)
            }
            FavoriteShelf(title = "Genres", values = profile.favoriteGenres)
            FavoriteShelf(title = "Artists", values = profile.favoriteArtists)
            FavoriteShelf(title = "Albums", values = profile.favoriteAlbums)
            FavoriteShelf(title = "Tracks", values = profile.favoriteTracks)
        }
    }
}

@Composable
private fun FavoriteShelf(title: String, values: List<String>) {
    if (values.isEmpty()) return
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            text = title.uppercase(),
            style = MaterialTheme.typography.labelLarge,
            color = JukePalette.Muted,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            values.take(3).forEach { FavoriteTag(label = it) }
        }
    }
}

@Composable
private fun SearchProfilesSection(
    query: String,
    results: List<ProfileSummary>,
    onQueryChange: (String) -> Unit,
    onSearchProfiles: () -> Unit,
    onSelectProfile: (ProfileSummary) -> Unit,
) {
    JukeCard {
        Column(
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(text = "Explore listeners", style = MaterialTheme.typography.titleLarge)
            JukeInputField(
                label = "Username",
                value = query,
                onValueChange = onQueryChange,
                placeholder = "Search by username",
            )
            JukeButton(
                onClick = onSearchProfiles,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 52.dp),
                enabled = query.trim().length >= 2,
            ) {
                Text(text = "Find profiles")
            }

            if (results.isNotEmpty()) {
                HorizontalDivider(color = JukePalette.Border)
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 260.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    items(results, key = { it.username }) { summary ->
                        ProfileResultRow(summary = summary, onSelectProfile = onSelectProfile)
                    }
                }
            }
        }
    }
}

@Composable
private fun ProfileResultRow(
    summary: ProfileSummary,
    onSelectProfile: (ProfileSummary) -> Unit,
) {
    Surface(
        shape = MaterialTheme.shapes.medium,
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.4f),
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp)
            .clickable { onSelectProfile(summary) },
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(text = summary.displayName, style = MaterialTheme.typography.titleMedium)
                Text(text = "@${summary.username}", style = MaterialTheme.typography.labelLarge, color = JukePalette.Muted)
                if (summary.tagline.isNotBlank()) {
                    Text(
                        text = summary.tagline,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
            Text(text = "View", color = JukePalette.Accent)
        }
    }
}

@Composable
private fun FavoriteTag(label: String) {
    Surface(
        shape = MaterialTheme.shapes.small,
        border = BorderStroke(1.dp, JukePalette.Border),
        color = JukePalette.PanelAlt.copy(alpha = 0.25f),
    ) {
        Text(
            text = label,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
            style = MaterialTheme.typography.labelLarge,
            color = JukePalette.Text,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Preview(showBackground = true)
@Composable
private fun ProfileScreenPreview() {
    val profile = MusicProfile(
        username = "listener",
        displayName = "Ambient Explorer",
        name = "",
        tagline = "Sub-bass pilgrim",
        bio = "I collect left-field jazz and doom metal.",
        location = "Brooklyn",
        avatarUrl = "",
        favoriteGenres = listOf("doom metal", "ambient"),
        favoriteArtists = listOf("Tool", "Boards of Canada"),
        favoriteAlbums = listOf("Lateralus"),
        favoriteTracks = listOf("Disposition"),
        onboardingCompletedAt = null,
        isOwner = true,
    )
    ProfileScreen(
        state = ProfileUiState(isLoading = false, profile = profile, focusedProfile = profile),
        onRefresh = {},
        onQueryChange = {},
        onSearchProfiles = {},
        onSelectProfile = {},
    )
}
