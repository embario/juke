package fm.juke.mobile.ui.onboarding

enum class OnboardingStep(val title: String, val subtitle: String, val isRequired: Boolean = false) {
    GENRES(
        "What are your top 3 genres?",
        "These help us understand your musical identity",
        isRequired = true,
    ),
    ARTIST(
        "Your ride-or-die artist?",
        "That one artist you'll defend to the end",
    ),
    HATED(
        "Any genres you can't stand?",
        "We'll make sure to avoid these",
    ),
    RAINY(
        "What's your rainy day soundtrack?",
        "When the mood is mellow",
    ),
    WORKOUT(
        "What powers your workout?",
        "Your energy anthem",
    ),
    DECADE(
        "What decade speaks to you?",
        "The era that shaped your taste",
    ),
    LISTENING(
        "How do you listen?",
        "Everyone has their style",
    ),
    AGE(
        "What's your age range?",
        "Helps us personalize your experience",
    ),
    LOCATION(
        "Where are you located?",
        "We'll place you on the Juke World map",
    ),
    CONNECT(
        "You're almost there!",
        "Save your profile to complete setup",
    );
}

data class OnboardingGenre(
    val id: String,
    val name: String,
    val spotifyId: String,
    val topArtists: List<GenreArtist>,
)

data class GenreArtist(val name: String, val imageUrl: String)

data class OnboardingArtist(
    val id: String,
    val name: String,
    val spotifyId: String,
    val imageUrl: String,
)

data class CityLocation(
    val name: String,
    val country: String,
    val lat: Double,
    val lng: Double,
)

data class MoodOption(val id: String, val label: String, val icon: String)
data class WorkoutVibe(val id: String, val label: String, val icon: String, val description: String)
data class DecadeOption(val id: String, val label: String, val vibe: String)

data class OnboardingData(
    var favoriteGenres: List<String> = emptyList(),
    var rideOrDieArtist: OnboardingArtist? = null,
    var hatedGenres: List<String> = emptyList(),
    var rainyDayMood: String? = null,
    var workoutVibe: String? = null,
    var favoriteDecade: String? = null,
    var listeningStyle: String? = null,
    var ageRange: String? = null,
    var location: CityLocation? = null,
)

val FALLBACK_FEATURED_GENRES = listOf(
    OnboardingGenre("hiphop", "Hip-Hop", "hip-hop", listOf(
        GenreArtist("Drake", ""),
        GenreArtist("Kendrick Lamar", ""),
        GenreArtist("J. Cole", ""),
    )),
    OnboardingGenre("rock", "Rock", "rock", listOf(
        GenreArtist("Foo Fighters", ""),
        GenreArtist("Green Day", ""),
        GenreArtist("Nirvana", ""),
    )),
    OnboardingGenre("pop", "Pop", "pop", listOf(
        GenreArtist("Taylor Swift", ""),
        GenreArtist("Dua Lipa", ""),
        GenreArtist("The Weeknd", ""),
    )),
    OnboardingGenre("rnb", "R&B", "r-n-b", listOf(
        GenreArtist("SZA", ""),
        GenreArtist("Frank Ocean", ""),
        GenreArtist("Daniel Caesar", ""),
    )),
    OnboardingGenre("electronic", "Electronic", "electronic", listOf(
        GenreArtist("Daft Punk", ""),
        GenreArtist("Calvin Harris", ""),
        GenreArtist("Disclosure", ""),
    )),
    OnboardingGenre("country", "Country", "country", listOf(
        GenreArtist("Morgan Wallen", ""),
        GenreArtist("Luke Combs", ""),
        GenreArtist("Chris Stapleton", ""),
    )),
    OnboardingGenre("jazz", "Jazz", "jazz", listOf(
        GenreArtist("Kamasi Washington", ""),
        GenreArtist("Robert Glasper", ""),
        GenreArtist("Esperanza Spalding", ""),
    )),
    OnboardingGenre("classical", "Classical", "classical", listOf(
        GenreArtist("Yo-Yo Ma", ""),
        GenreArtist("Lang Lang", ""),
        GenreArtist("Hilary Hahn", ""),
    )),
    OnboardingGenre("latin", "Latin", "latin", listOf(
        GenreArtist("Bad Bunny", ""),
        GenreArtist("J Balvin", ""),
        GenreArtist("Rosalía", ""),
    )),
    OnboardingGenre("indie", "Indie", "indie", listOf(
        GenreArtist("Tame Impala", ""),
        GenreArtist("Arctic Monkeys", ""),
        GenreArtist("Mac DeMarco", ""),
    )),
)

val RAINY_DAY_MOODS = listOf(
    MoodOption("mellow", "Mellow & Acoustic", "🌧️"),
    MoodOption("jazz", "Jazz & Lo-fi", "☕"),
    MoodOption("indie", "Indie & Chill", "🌿"),
    MoodOption("classical", "Classical & Ambient", "🎻"),
    MoodOption("rnb", "R&B & Soul", "💜"),
)

val WORKOUT_VIBES = listOf(
    WorkoutVibe("intense", "Maximum Intensity", "🔥", "Heavy bass, fast tempo"),
    WorkoutVibe("hiphop", "Hip-Hop Energy", "💪", "Beats that hit hard"),
    WorkoutVibe("rock", "Rock Power", "🎸", "Guitar-driven adrenaline"),
    WorkoutVibe("edm", "EDM Drops", "⚡", "Build-ups and releases"),
    WorkoutVibe("pop", "Pop Anthems", "🎤", "Sing-along motivation"),
)

val DECADES = listOf(
    DecadeOption("60s", "60s", "Psychedelic & Soul"),
    DecadeOption("70s", "70s", "Disco & Punk"),
    DecadeOption("80s", "80s", "Synth & New Wave"),
    DecadeOption("90s", "90s", "Grunge & Golden Era"),
    DecadeOption("2000s", "2000s", "Pop Punk & Crunk"),
    DecadeOption("2010s", "2010s", "EDM & Streaming"),
    DecadeOption("2020s", "2020s", "Hyperpop & Revival"),
)

val AGE_RANGES = listOf("18-24", "25-34", "35-44", "45-54", "55+")

val CITIES = listOf(
    CityLocation("New York", "USA", 40.71, -74.01),
    CityLocation("Los Angeles", "USA", 34.05, -118.24),
    CityLocation("Chicago", "USA", 41.88, -87.63),
    CityLocation("Houston", "USA", 29.76, -95.37),
    CityLocation("Phoenix", "USA", 33.45, -112.07),
    CityLocation("London", "UK", 51.51, -0.13),
    CityLocation("Paris", "France", 48.86, 2.35),
    CityLocation("Tokyo", "Japan", 35.68, 139.69),
    CityLocation("Sydney", "Australia", -33.87, 151.21),
    CityLocation("Toronto", "Canada", 43.65, -79.38),
    CityLocation("Berlin", "Germany", 52.52, 13.41),
    CityLocation("Amsterdam", "Netherlands", 52.37, 4.90),
    CityLocation("Seoul", "South Korea", 37.57, 126.98),
    CityLocation("Singapore", "Singapore", 1.35, 103.82),
    CityLocation("Dubai", "UAE", 25.20, 55.27),
    CityLocation("Mumbai", "India", 19.08, 72.88),
    CityLocation("São Paulo", "Brazil", -23.55, -46.63),
    CityLocation("Mexico City", "Mexico", 19.43, -99.13),
    CityLocation("Lagos", "Nigeria", 6.52, 3.38),
    CityLocation("Cairo", "Egypt", 30.04, 31.24),
    CityLocation("Austin", "USA", 30.27, -97.74),
    CityLocation("Nashville", "USA", 36.16, -86.78),
    CityLocation("Atlanta", "USA", 33.75, -84.39),
    CityLocation("Miami", "USA", 25.76, -80.19),
    CityLocation("Seattle", "USA", 47.61, -122.33),
    CityLocation("San Francisco", "USA", 37.77, -122.42),
    CityLocation("Denver", "USA", 39.74, -104.99),
    CityLocation("Boston", "USA", 42.36, -71.06),
    CityLocation("Philadelphia", "USA", 39.95, -75.17),
    CityLocation("Detroit", "USA", 42.33, -83.05),
)

fun searchCities(query: String): List<CityLocation> {
    val trimmed = query.trim().lowercase()
    if (trimmed.isEmpty()) return emptyList()
    return CITIES.filter {
        it.name.lowercase().contains(trimmed) || it.country.lowercase().contains(trimmed)
    }.take(10)
}
