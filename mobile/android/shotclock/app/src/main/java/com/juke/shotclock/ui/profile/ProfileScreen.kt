package com.juke.shotclock.ui.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.juke.shotclock.core.design.ShotClockPalette
import com.juke.shotclock.core.design.components.SCStatusVariant
import com.juke.shotclock.core.design.components.ShotClockCard
import com.juke.shotclock.core.design.components.ShotClockChip
import com.juke.shotclock.core.design.components.ShotClockSpinner
import com.juke.shotclock.core.design.components.ShotClockStatusBanner
import com.juke.shotclock.model.MusicProfile

@Composable
fun ProfileRoute(viewModel: ProfileViewModel = viewModel()) {
    ProfileScreen(
        state = viewModel.uiState,
        onRetry = viewModel::loadProfile,
    )
}

@Composable
private fun ProfileScreen(
    state: ProfileUiState,
    onRetry: () -> Unit,
) {
    when {
        state.isLoading -> {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center,
            ) {
                ShotClockSpinner()
            }
        }
        state.error != null -> {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(24.dp),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                ShotClockStatusBanner(
                    message = state.error,
                    variant = SCStatusVariant.ERROR,
                )
            }
        }
        state.profile != null -> {
            ProfileContent(profile = state.profile)
        }
        else -> {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = "No profile data available.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = ShotClockPalette.Muted,
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ProfileContent(profile: MusicProfile) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp, vertical = 16.dp),
    ) {
        // Header
        ShotClockCard {
            Text(
                text = profile.displayName.ifBlank { profile.username },
                style = MaterialTheme.typography.headlineLarge,
                color = ShotClockPalette.Text,
            )
            if (profile.tagline.isNotBlank()) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = profile.tagline,
                    style = MaterialTheme.typography.titleMedium,
                    color = ShotClockPalette.AccentSoft,
                )
            }
            if (profile.bio.isNotBlank()) {
                Spacer(modifier = Modifier.height(12.dp))
                Text(
                    text = profile.bio,
                    style = MaterialTheme.typography.bodyMedium,
                    color = ShotClockPalette.Muted,
                )
            }
        }

        // Favorite Genres
        if (profile.favoriteGenres.isNotEmpty()) {
            Spacer(modifier = Modifier.height(24.dp))
            SectionHeader(title = "Favorite Genres")
            Spacer(modifier = Modifier.height(8.dp))
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                profile.favoriteGenres.forEach { genre ->
                    ShotClockChip(
                        label = genre,
                        selected = true,
                        accentColor = ShotClockPalette.Secondary,
                        onClick = {},
                    )
                }
            }
        }

        // Favorite Artists
        if (profile.favoriteArtists.isNotEmpty()) {
            Spacer(modifier = Modifier.height(24.dp))
            SectionHeader(title = "Favorite Artists")
            Spacer(modifier = Modifier.height(8.dp))
            FavoriteList(items = profile.favoriteArtists)
        }

        // Favorite Albums
        if (profile.favoriteAlbums.isNotEmpty()) {
            Spacer(modifier = Modifier.height(24.dp))
            SectionHeader(title = "Favorite Albums")
            Spacer(modifier = Modifier.height(8.dp))
            FavoriteList(items = profile.favoriteAlbums)
        }

        // Favorite Tracks
        if (profile.favoriteTracks.isNotEmpty()) {
            Spacer(modifier = Modifier.height(24.dp))
            SectionHeader(title = "Favorite Tracks")
            Spacer(modifier = Modifier.height(8.dp))
            FavoriteList(items = profile.favoriteTracks)
        }

        Spacer(modifier = Modifier.height(32.dp))
    }
}

@Composable
private fun SectionHeader(title: String) {
    Text(
        text = title.uppercase(),
        style = MaterialTheme.typography.labelLarge,
        color = ShotClockPalette.Muted,
        modifier = Modifier.padding(start = 4.dp),
    )
}

@Composable
private fun FavoriteList(items: List<String>) {
    ShotClockCard {
        items.forEachIndexed { index, item ->
            Text(
                text = item,
                style = MaterialTheme.typography.bodyMedium,
                color = ShotClockPalette.Text,
            )
            if (index < items.lastIndex) {
                Spacer(modifier = Modifier.height(10.dp))
            }
        }
    }
}
