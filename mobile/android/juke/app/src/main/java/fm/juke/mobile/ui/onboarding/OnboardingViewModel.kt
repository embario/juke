package fm.juke.mobile.ui.onboarding

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import android.util.Log
import fm.juke.mobile.core.di.ServiceLocator
import fm.juke.mobile.data.network.humanReadableMessage
import fm.juke.mobile.data.repository.CatalogRepository
import fm.juke.mobile.data.repository.ProfileRepository
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject

private val ALL_STEPS = OnboardingStep.values().toList()

data class OnboardingUiState(
    val currentStep: OnboardingStep = OnboardingStep.GENRES,
    val data: OnboardingData = OnboardingData(),
    val isSubmitting: Boolean = false,
    val error: String? = null,
    val featuredGenres: List<OnboardingGenre> = emptyList(),
    val isLoadingFeaturedGenres: Boolean = false,
    // Artist search
    val artistQuery: String = "",
    val artistResults: List<OnboardingArtist> = emptyList(),
    val isSearchingArtists: Boolean = false,
) {
    val currentStepIndex: Int get() = ALL_STEPS.indexOf(currentStep)
    val totalSteps: Int get() = ALL_STEPS.size
    val progress: Double get() = (currentStepIndex + 1).toDouble() / totalSteps * 100
    val canGoBack: Boolean get() = currentStepIndex > 0
    val canGoNext: Boolean get() = currentStepIndex < totalSteps - 1
}

class OnboardingViewModel(
    private val profileRepository: ProfileRepository = ServiceLocator.profileRepository,
    private val catalogRepository: CatalogRepository = ServiceLocator.catalogRepository,
) : ViewModel() {

    var uiState by mutableStateOf(OnboardingUiState())
        private set

    init {
        loadFeaturedGenres()
    }

    private fun loadFeaturedGenres() {
        viewModelScope.launch {
            uiState = uiState.copy(isLoadingFeaturedGenres = true)
            catalogRepository.featuredGenres()
                .onSuccess { genres ->
                    Log.d("Onboarding", "Loaded featured genres=${genres.size}, firstImage=${genres.firstOrNull()?.topArtists?.firstOrNull()?.imageUrl.orEmpty()}")
                    uiState = uiState.copy(
                        featuredGenres = genres.map { genre ->
                            OnboardingGenre(
                                id = genre.id,
                                name = genre.name,
                                spotifyId = genre.spotifyId,
                                topArtists = genre.topArtists.map { artist ->
                                    GenreArtist(
                                        name = artist.name,
                                        imageUrl = artist.imageUrl,
                                    )
                                },
                            )
                        },
                        isLoadingFeaturedGenres = false,
                    )
                }
                .onFailure {
                    uiState = uiState.copy(isLoadingFeaturedGenres = false)
                }
        }
    }

    fun goNext() {
        if (!uiState.canGoNext) return
        uiState = uiState.copy(
            currentStep = ALL_STEPS[uiState.currentStepIndex + 1],
            error = null,
        )
    }

    fun goBack() {
        if (!uiState.canGoBack) return
        uiState = uiState.copy(currentStep = ALL_STEPS[uiState.currentStepIndex - 1])
    }

    fun restart() {
        uiState = OnboardingUiState()
    }

    // --- Genre toggles ---

    fun toggleFavoriteGenre(genreId: String) {
        val genres = uiState.data.favoriteGenres.toMutableList()
        if (genreId in genres) {
            genres.remove(genreId)
        } else if (genres.size < 3) {
            genres.add(genreId)
        }
        uiState = uiState.copy(data = uiState.data.copy(favoriteGenres = genres))
    }

    fun toggleHatedGenre(genreId: String) {
        val genres = uiState.data.hatedGenres.toMutableList()
        if (genreId in genres) {
            genres.remove(genreId)
        } else if (genres.size < 3) {
            genres.add(genreId)
        }
        uiState = uiState.copy(data = uiState.data.copy(hatedGenres = genres))
    }

    // --- Artist search ---

    fun updateArtistQuery(query: String) {
        uiState = uiState.copy(artistQuery = query)
        if (query.trim().length >= 2) {
            searchArtists(query.trim())
        } else {
            uiState = uiState.copy(artistResults = emptyList(), isSearchingArtists = false)
        }
    }

    private fun searchArtists(query: String) {
        viewModelScope.launch {
            uiState = uiState.copy(isSearchingArtists = true)
            catalogRepository.searchArtists(query)
                .onSuccess { artists ->
                    uiState = uiState.copy(
                        isSearchingArtists = false,
                        artistResults = artists.take(10).map { a ->
                            OnboardingArtist(
                                id = a.id.toString(),
                                name = a.name,
                                spotifyId = a.spotifyUri,
                                imageUrl = a.imageUrl,
                            )
                        },
                    )
                }
                .onFailure {
                    uiState = uiState.copy(isSearchingArtists = false, artistResults = emptyList())
                }
        }
    }

    fun selectArtist(artist: OnboardingArtist) {
        uiState = uiState.copy(
            data = uiState.data.copy(rideOrDieArtist = artist),
            artistQuery = "",
            artistResults = emptyList(),
        )
    }

    fun clearArtist() {
        uiState = uiState.copy(data = uiState.data.copy(rideOrDieArtist = null))
    }

    // --- Simple setters ---

    fun setRainyDayMood(mood: String?) {
        uiState = uiState.copy(data = uiState.data.copy(rainyDayMood = mood))
    }

    fun setWorkoutVibe(vibe: String?) {
        uiState = uiState.copy(data = uiState.data.copy(workoutVibe = vibe))
    }

    fun setFavoriteDecade(decade: String?) {
        uiState = uiState.copy(data = uiState.data.copy(favoriteDecade = decade))
    }

    fun setListeningStyle(style: String?) {
        uiState = uiState.copy(data = uiState.data.copy(listeningStyle = style))
    }

    fun setAgeRange(range: String?) {
        uiState = uiState.copy(data = uiState.data.copy(ageRange = range))
    }

    fun setLocation(city: CityLocation?) {
        uiState = uiState.copy(data = uiState.data.copy(location = city))
    }

    // --- Save & complete ---

    fun saveAndFinish(onComplete: (CityLocation?) -> Unit) {
        viewModelScope.launch {
            uiState = uiState.copy(isSubmitting = true, error = null)
            val data = uiState.data
            val completedAt = java.time.Instant.now().toString()
            val body = buildJsonObject {
                putJsonArray("favorite_genres") {
                    data.favoriteGenres.forEach { add(JsonPrimitive(it)) }
                }
                putJsonArray("favorite_artists") {
                    data.rideOrDieArtist?.let { add(JsonPrimitive(it.spotifyId)) }
                }
                put("location", data.location?.name ?: "")
                data.location?.let {
                    put("city_lat", it.lat)
                    put("city_lng", it.lng)
                }
                put("onboarding_completed_at", completedAt)
                putJsonObject("custom_data") {
                    putJsonArray("hated_genres") {
                        data.hatedGenres.forEach { add(JsonPrimitive(it)) }
                    }
                    data.rainyDayMood?.let { put("rainy_day_mood", it) }
                    data.workoutVibe?.let { put("workout_vibe", it) }
                    data.favoriteDecade?.let { put("favorite_decade", it) }
                    data.listeningStyle?.let { put("listening_style", it) }
                    data.ageRange?.let { put("age_range", it) }
                }
            }

            profileRepository.patchProfile(body)
                .onSuccess {
                    ServiceLocator.sessionStore.setOnboardingCompletedAt(completedAt)
                    uiState = uiState.copy(isSubmitting = false)
                    onComplete(data.location)
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(isSubmitting = false, error = throwable.humanReadableMessage())
                }
        }
    }
}
