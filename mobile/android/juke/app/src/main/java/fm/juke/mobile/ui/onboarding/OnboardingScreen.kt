package fm.juke.mobile.ui.onboarding

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items as lazyItems
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import coil.compose.AsyncImage
import coil.request.ImageRequest
import android.util.Log
import fm.juke.mobile.core.design.JukePalette
import fm.juke.mobile.core.design.components.JukeBackground
import fm.juke.mobile.core.design.components.JukeButton
import fm.juke.mobile.core.design.components.JukeButtonVariant
import fm.juke.mobile.core.design.components.JukeChip
import fm.juke.mobile.core.design.components.JukeInputField
import fm.juke.mobile.core.design.components.JukeSpinner
import fm.juke.mobile.core.design.components.JukeStatusBanner
import fm.juke.mobile.core.design.components.JukeStatusVariant

@Composable
fun OnboardingRoute(
    viewModel: OnboardingViewModel = viewModel(),
    onComplete: (CityLocation?) -> Unit,
) {
    val state = viewModel.uiState
    OnboardingScreen(
        state = state,
        onGoBack = viewModel::goBack,
        onGoNext = viewModel::goNext,
        onRestart = viewModel::restart,
        onToggleFavoriteGenre = viewModel::toggleFavoriteGenre,
        onToggleHatedGenre = viewModel::toggleHatedGenre,
        onArtistQueryChange = viewModel::updateArtistQuery,
        onSelectArtist = viewModel::selectArtist,
        onClearArtist = viewModel::clearArtist,
        onSetRainyDayMood = viewModel::setRainyDayMood,
        onSetWorkoutVibe = viewModel::setWorkoutVibe,
        onSetFavoriteDecade = viewModel::setFavoriteDecade,
        onSetListeningStyle = viewModel::setListeningStyle,
        onSetAgeRange = viewModel::setAgeRange,
        onSetLocation = viewModel::setLocation,
        onSaveAndFinish = { viewModel.saveAndFinish(onComplete) },
    )
}

@Composable
fun OnboardingScreen(
    state: OnboardingUiState,
    onGoBack: () -> Unit,
    onGoNext: () -> Unit,
    onRestart: () -> Unit,
    onToggleFavoriteGenre: (String) -> Unit,
    onToggleHatedGenre: (String) -> Unit,
    onArtistQueryChange: (String) -> Unit,
    onSelectArtist: (OnboardingArtist) -> Unit,
    onClearArtist: () -> Unit,
    onSetRainyDayMood: (String?) -> Unit,
    onSetWorkoutVibe: (String?) -> Unit,
    onSetFavoriteDecade: (String?) -> Unit,
    onSetListeningStyle: (String?) -> Unit,
    onSetAgeRange: (String?) -> Unit,
    onSetLocation: (CityLocation?) -> Unit,
    onSaveAndFinish: () -> Unit,
) {
    JukeBackground {
        Column(modifier = Modifier.fillMaxSize()) {
            LinearProgressIndicator(
                progress = { (state.progress / 100.0).toFloat() },
                modifier = Modifier.fillMaxWidth(),
                color = JukePalette.Accent,
                trackColor = JukePalette.PanelAlt,
            )
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 24.dp, vertical = 32.dp),
                verticalArrangement = Arrangement.spacedBy(24.dp),
            ) {
                StepHeader(state, onGoBack, onRestart)

                when (state.currentStep) {
                    OnboardingStep.GENRES -> GenreStep(state, onToggleFavoriteGenre)
                    OnboardingStep.ARTIST -> ArtistStep(state, onArtistQueryChange, onSelectArtist, onClearArtist)
                    OnboardingStep.HATED -> HatedGenresStep(state, onToggleHatedGenre)
                    OnboardingStep.RAINY -> MoodStep(state.data.rainyDayMood, RAINY_DAY_MOODS, onSetRainyDayMood)
                    OnboardingStep.WORKOUT -> WorkoutStep(state, onSetWorkoutVibe)
                    OnboardingStep.DECADE -> DecadeStep(state, onSetFavoriteDecade)
                    OnboardingStep.LISTENING -> ListeningStyleStep(state, onSetListeningStyle)
                    OnboardingStep.AGE -> AgeRangeStep(state, onSetAgeRange)
                    OnboardingStep.LOCATION -> LocationStep(state, onSetLocation)
                    OnboardingStep.CONNECT -> ConnectStep(state, onSaveAndFinish)
                }

                StepFooter(state, onGoNext)
            }
        }
    }
}

@Composable
private fun StepHeader(
    state: OnboardingUiState,
    onGoBack: () -> Unit,
    onRestart: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (state.canGoBack && state.currentStep != OnboardingStep.CONNECT) {
                IconButton(onClick = onGoBack) {
                    Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Back", tint = JukePalette.Text)
                }
            } else {
                Spacer(modifier = Modifier.width(48.dp))
            }
            Spacer(modifier = Modifier.weight(1f))
            IconButton(onClick = onRestart) {
                Icon(Icons.Outlined.Refresh, "Restart", tint = JukePalette.Muted)
            }
        }

        Text(
            text = "Step ${state.currentStepIndex + 1} of ${state.totalSteps}",
            style = MaterialTheme.typography.labelLarge,
            color = JukePalette.Muted,
            modifier = Modifier.padding(start = 4.dp),
        )
        Text(
            text = state.currentStep.title,
            style = MaterialTheme.typography.headlineLarge,
            color = JukePalette.Text,
            modifier = Modifier.padding(start = 4.dp),
        )
        Text(
            text = state.currentStep.subtitle,
            style = MaterialTheme.typography.bodyMedium,
            color = JukePalette.Muted,
            modifier = Modifier.padding(start = 4.dp),
        )
    }
}

@Composable
private fun StepFooter(state: OnboardingUiState, onGoNext: () -> Unit) {
    if (state.currentStep == OnboardingStep.CONNECT) return
    Row(
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        if (!state.currentStep.isRequired) {
            JukeButton(
                onClick = onGoNext,
                modifier = Modifier.weight(1f).height(52.dp),
                variant = JukeButtonVariant.GHOST,
            ) {
                Text(text = "Skip")
            }
        }
        JukeButton(
            onClick = onGoNext,
            modifier = Modifier.weight(1f).height(52.dp),
            enabled = !(state.currentStep == OnboardingStep.GENRES && state.data.favoriteGenres.isEmpty()),
        ) {
            Text(text = "Continue")
        }
    }
}

// --- Genre Step ---

@Composable
private fun GenreStep(state: OnboardingUiState, onToggle: (String) -> Unit) {
    val genres = if (state.featuredGenres.isNotEmpty()) {
        state.featuredGenres
    } else {
        FALLBACK_FEATURED_GENRES
    }
    LazyVerticalGrid(
        columns = GridCells.Adaptive(140.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.heightIn(max = 600.dp),
    ) {
        gridItems(genres) { genre ->
            val isSelected = genre.id in state.data.favoriteGenres
            val isDisabled = state.data.favoriteGenres.size >= 3 && !isSelected
            SelectionCard(
                selected = isSelected,
                enabled = !isDisabled,
                onClick = { onToggle(genre.id) },
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    genre.topArtists.take(3).forEachIndexed { idx, topArtist ->
                        OnboardingArtistImage(
                            url = topArtist.imageUrl,
                            contentDescription = topArtist.name,
                            modifier = Modifier
                                .size(36.dp)
                                .clip(CircleShape)
                                .offset(x = -8.dp * idx),
                        )
                    }
                }
                Text(
                    text = genre.name,
                    style = MaterialTheme.typography.titleMedium,
                    color = if (isSelected) JukePalette.Accent else JukePalette.Text,
                )
                Text(
                    text = genre.topArtists.joinToString(", ") { it.name },
                    style = MaterialTheme.typography.bodySmall,
                    color = JukePalette.Muted,
                    maxLines = 2,
                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                )
            }
        }
    }
    Text(
        text = "${state.data.favoriteGenres.size}/3 selected",
        style = MaterialTheme.typography.bodySmall,
        color = JukePalette.Muted,
        modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
    )
}

// --- Artist Step ---

@Composable
private fun ArtistStep(
    state: OnboardingUiState,
    onQueryChange: (String) -> Unit,
    onSelect: (OnboardingArtist) -> Unit,
    onClear: () -> Unit,
) {
    val artist = state.data.rideOrDieArtist
    if (artist != null) {
        SelectedArtistCard(artist, onClear)
    } else {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            JukeInputField(
                label = "Search Artist",
                value = state.artistQuery,
                onValueChange = onQueryChange,
                placeholder = "Search for an artist…",
            )
            when {
                state.isSearchingArtists -> {
                    Text("Searching…", style = MaterialTheme.typography.bodyMedium, color = JukePalette.Muted)
                }
                state.artistResults.isNotEmpty() -> {
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = JukePalette.PanelAlt,
                    ) {
                        LazyColumn(modifier = Modifier.heightIn(max = 260.dp)) {
                            lazyItems(state.artistResults, key = { it.id }) { result ->
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable { onSelect(result) }
                                        .padding(12.dp),
                                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    OnboardingArtistImage(
                                        url = result.imageUrl,
                                        contentDescription = result.name,
                                        modifier = Modifier.size(40.dp).clip(CircleShape),
                                    )
                                    Text(result.name, style = MaterialTheme.typography.bodyMedium, color = JukePalette.Text)
                                }
                                HorizontalDivider(color = JukePalette.Border, modifier = Modifier.padding(start = 64.dp))
                            }
                        }
                    }
                }
                state.artistQuery.trim().isNotEmpty() -> {
                    Text("No artists found", style = MaterialTheme.typography.bodyMedium, color = JukePalette.Muted)
                }
            }
        }
    }
}

@Composable
private fun SelectedArtistCard(artist: OnboardingArtist, onClear: () -> Unit) {
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = JukePalette.PanelAlt,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OnboardingArtistImage(
                url = artist.imageUrl,
                contentDescription = artist.name,
                modifier = Modifier.size(64.dp).clip(RoundedCornerShape(12.dp)),
            )
            Column(modifier = Modifier.weight(1f)) {
                Text(artist.name, style = MaterialTheme.typography.titleMedium, color = JukePalette.Text)
                Text("Your ride-or-die", style = MaterialTheme.typography.bodySmall, color = JukePalette.Muted)
            }
            IconButton(onClick = onClear) {
                Icon(Icons.Outlined.Close, "Remove", tint = JukePalette.Muted)
            }
        }
    }
}

// --- Hated Genres Step ---

@Composable
private fun HatedGenresStep(state: OnboardingUiState, onToggle: (String) -> Unit) {
    val genres = if (state.featuredGenres.isNotEmpty()) {
        state.featuredGenres
    } else {
        FALLBACK_FEATURED_GENRES
    }
    val available = genres.filter { it.id !in state.data.favoriteGenres }
    LazyVerticalGrid(
        columns = GridCells.Adaptive(140.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.heightIn(max = 500.dp),
    ) {
        gridItems(available) { genre ->
            val isSelected = genre.id in state.data.hatedGenres
            val isDisabled = state.data.hatedGenres.size >= 3 && !isSelected
            SelectionCard(selected = isSelected, enabled = !isDisabled, onClick = { onToggle(genre.id) }) {
                Text(
                    text = genre.name,
                    style = MaterialTheme.typography.titleMedium,
                    color = if (isSelected) JukePalette.Accent else JukePalette.Text,
                )
                Text(
                    text = genre.topArtists.joinToString(", ") { it.name },
                    style = MaterialTheme.typography.bodySmall,
                    color = JukePalette.Muted,
                    maxLines = 2,
                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                )
            }
        }
    }
    Text(
        text = "${state.data.hatedGenres.size}/3 selected (optional)",
        style = MaterialTheme.typography.bodySmall,
        color = JukePalette.Muted,
        modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
    )
}

// --- Mood Step (Rainy Day) ---

@Composable
private fun MoodStep(selected: String?, options: List<MoodOption>, onSelect: (String?) -> Unit) {
    LazyVerticalGrid(
        columns = GridCells.Adaptive(140.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.heightIn(max = 400.dp),
    ) {
        gridItems(options) { option ->
            val isSelected = selected == option.id
            SelectionCard(selected = isSelected, onClick = { onSelect(if (isSelected) null else option.id) }) {
                Text(option.icon, style = MaterialTheme.typography.displayMedium)
                Text(
                    text = option.label,
                    style = MaterialTheme.typography.titleSmall,
                    color = if (isSelected) JukePalette.Accent else JukePalette.Text,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                )
            }
        }
    }
}

// --- Workout Step ---

@Composable
private fun WorkoutStep(state: OnboardingUiState, onSelect: (String?) -> Unit) {
    LazyVerticalGrid(
        columns = GridCells.Adaptive(140.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.heightIn(max = 400.dp),
    ) {
        gridItems(WORKOUT_VIBES) { vibe ->
            val isSelected = state.data.workoutVibe == vibe.id
            SelectionCard(selected = isSelected, onClick = { onSelect(if (isSelected) null else vibe.id) }) {
                Text(vibe.icon, style = MaterialTheme.typography.displayMedium)
                Text(
                    text = vibe.label,
                    style = MaterialTheme.typography.titleSmall,
                    color = if (isSelected) JukePalette.Accent else JukePalette.Text,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                )
                Text(
                    text = vibe.description,
                    style = MaterialTheme.typography.bodySmall,
                    color = JukePalette.Muted,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                )
            }
        }
    }
}

// --- Decade Step ---

@Composable
private fun DecadeStep(state: OnboardingUiState, onSelect: (String?) -> Unit) {
    LazyVerticalGrid(
        columns = GridCells.Adaptive(100.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier.heightIn(max = 400.dp),
    ) {
        gridItems(DECADES) { decade ->
            val isSelected = state.data.favoriteDecade == decade.id
            SelectionCard(selected = isSelected, onClick = { onSelect(if (isSelected) null else decade.id) }) {
                Text(
                    text = decade.label,
                    style = MaterialTheme.typography.titleMedium,
                    color = if (isSelected) JukePalette.Accent else JukePalette.Text,
                )
                Text(
                    text = decade.vibe,
                    style = MaterialTheme.typography.bodySmall,
                    color = JukePalette.Muted,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                )
            }
        }
    }
}

// --- Listening Style Step ---

@Composable
private fun ListeningStyleStep(state: OnboardingUiState, onSelect: (String?) -> Unit) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        ListeningStyleCard("playlist", "🔀", "Playlist Person", "Curated vibes, shuffle on, discover new tracks", state.data.listeningStyle, onSelect, Modifier.weight(1f))
        ListeningStyleCard("album", "💿", "Album Listener", "Front to back, the way it was meant to be heard", state.data.listeningStyle, onSelect, Modifier.weight(1f))
    }
}

@Composable
private fun ListeningStyleCard(id: String, icon: String, title: String, desc: String, selected: String?, onSelect: (String?) -> Unit, modifier: Modifier = Modifier) {
    val isSelected = selected == id
    SelectionCard(selected = isSelected, onClick = { onSelect(if (isSelected) null else id) }, modifier = modifier) {
        Text(icon, style = MaterialTheme.typography.displayMedium)
        Text(
            text = title,
            style = MaterialTheme.typography.titleSmall,
            color = if (isSelected) JukePalette.Accent else JukePalette.Text,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
        )
        Text(text = desc, style = MaterialTheme.typography.bodySmall, color = JukePalette.Muted, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
    }
}

// --- Age Range Step ---

@Composable
private fun AgeRangeStep(state: OnboardingUiState, onSelect: (String?) -> Unit) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        AGE_RANGES.forEach { range ->
            val isSelected = state.data.ageRange == range
            JukeChip(
                label = range,
                selected = isSelected,
                onClick = { onSelect(if (isSelected) null else range) },
            )
        }
    }
}

// --- Location Step ---

@Composable
private fun LocationStep(state: OnboardingUiState, onSelect: (CityLocation?) -> Unit) {
    val city = state.data.location
    if (city != null) {
        SelectedLocationCard(city, onSelect)
    } else {
        LocationSearchSurface(onSelect)
    }
}

@Composable
private fun SelectedLocationCard(city: CityLocation, onSelect: (CityLocation?) -> Unit) {
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = JukePalette.PanelAlt,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Outlined.LocationOn, "Location", tint = JukePalette.Accent, modifier = Modifier.size(32.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(city.name, style = MaterialTheme.typography.titleMedium, color = JukePalette.Text)
                Text(city.country, style = MaterialTheme.typography.bodySmall, color = JukePalette.Muted)
            }
            IconButton(onClick = { onSelect(null) }) {
                Icon(Icons.Outlined.Close, "Remove", tint = JukePalette.Muted)
            }
        }
    }
}

@Composable
private fun LocationSearchSurface(onSelect: (CityLocation?) -> Unit) {
    var query by remember { mutableStateOf("") }
    val results = remember(query) { searchCities(query) }

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        JukeInputField(
            label = "Search City",
            value = query,
            onValueChange = { query = it },
            placeholder = "Type a city or country…",
        )
        if (results.isNotEmpty()) {
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = JukePalette.PanelAlt,
            ) {
                LazyColumn(modifier = Modifier.heightIn(max = 260.dp)) {
                    lazyItems(results, key = { "${it.name}-${it.country}" }) { city ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { onSelect(city) }
                                .padding(12.dp),
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(Icons.Outlined.LocationOn, "Location", tint = JukePalette.Muted, modifier = Modifier.size(20.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Text(city.name, style = MaterialTheme.typography.bodyMedium, color = JukePalette.Text)
                                Text(city.country, style = MaterialTheme.typography.bodySmall, color = JukePalette.Muted)
                            }
                        }
                        HorizontalDivider(color = JukePalette.Border, modifier = Modifier.padding(start = 44.dp))
                    }
                }
            }
        }
    }
}

// --- Connect Step ---

@Composable
private fun ConnectStep(state: OnboardingUiState, onSave: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = JukePalette.PanelAlt,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(modifier = Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                SummaryRow("Genres", state.data.favoriteGenres.joinToString(", ").ifEmpty { "None" })
                state.data.rideOrDieArtist?.let { SummaryRow("Ride-or-Die", it.name) }
                if (state.data.hatedGenres.isNotEmpty()) SummaryRow("Hated", state.data.hatedGenres.joinToString(", "))
                state.data.rainyDayMood?.let { SummaryRow("Rainy Day", RAINY_DAY_MOODS.find { m -> m.id == it }?.label ?: it) }
                state.data.workoutVibe?.let { SummaryRow("Workout", WORKOUT_VIBES.find { v -> v.id == it }?.label ?: it) }
                state.data.favoriteDecade?.let { SummaryRow("Decade", it) }
                state.data.listeningStyle?.let { SummaryRow("Style", if (it == "playlist") "Playlist Person" else "Album Listener") }
                state.data.ageRange?.let { SummaryRow("Age", it) }
                state.data.location?.let { SummaryRow("Location", "${it.name}, ${it.country}") }
            }
        }

        state.error?.let { error ->
            JukeStatusBanner(message = error, variant = JukeStatusVariant.ERROR)
        }

        JukeButton(
            onClick = onSave,
            modifier = Modifier.fillMaxWidth().height(56.dp),
            enabled = !state.isSubmitting,
        ) {
            if (state.isSubmitting) {
                JukeSpinner()
            } else {
                Text("Enter Juke World")
            }
        }
    }
}

@Composable
private fun SummaryRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.labelLarge, color = JukePalette.Muted)
        Text(value, style = MaterialTheme.typography.bodyMedium, color = JukePalette.Text)
    }
}

// --- Reusable selection card ---

@Composable
private fun SelectionCard(
    selected: Boolean,
    onClick: () -> Unit,
    enabled: Boolean = true,
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit,
) {
    val borderColor = if (selected) JukePalette.Accent else JukePalette.Border
    val bgColor = if (selected) JukePalette.Accent.copy(alpha = 0.15f) else JukePalette.PanelAlt
    Surface(
        shape = RoundedCornerShape(16.dp),
        color = bgColor,
        border = BorderStroke(1.dp, borderColor),
        modifier = modifier.clickable(enabled = enabled) { onClick() }.heightIn(min = 80.dp),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            content()
        }
    }
}

@Composable
private fun CirclePlaceholder(): androidx.compose.ui.graphics.painter.Painter {
    return remember {
        object : androidx.compose.ui.graphics.painter.Painter() {
            override val intrinsicSize = androidx.compose.ui.geometry.Size(36f, 36f)
            override fun androidx.compose.ui.graphics.drawscope.DrawScope.onDraw() {
                drawCircle(JukePalette.PanelAlt)
            }
        }
    }
}

@Composable
private fun OnboardingArtistImage(
    url: String,
    contentDescription: String,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val placeholder = CirclePlaceholder()
    AsyncImage(
        model = ImageRequest.Builder(context)
            .data(url.ifBlank { null })
            .crossfade(true)
            .allowHardware(false)
            .listener(
                onStart = {
                    if (url.isNotBlank()) {
                        Log.d("OnboardingImage", "Loading image: $url")
                    }
                },
                onSuccess = { _, _ ->
                    if (url.isNotBlank()) {
                        Log.d("OnboardingImage", "Loaded image: $url")
                    }
                },
                onError = { _, error ->
                    if (url.isNotBlank()) {
                        Log.w("OnboardingImage", "Failed to load image: $url", error.throwable)
                    }
                },
            )
            .build(),
        contentDescription = contentDescription,
        modifier = modifier,
        placeholder = placeholder,
        error = placeholder,
        contentScale = ContentScale.Crop,
    )
}
