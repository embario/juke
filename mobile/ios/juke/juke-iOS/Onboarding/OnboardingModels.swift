import Foundation

// MARK: - Step identifiers (ordered)

enum OnboardingStep: String, CaseIterable, Identifiable {
    case genres
    case artist
    case hated
    case rainy
    case workout
    case decade
    case listening
    case age
    case location
    case connect

    var id: Self { self }

    var title: String {
        switch self {
        case .genres:    return "What are your top 3 genres?"
        case .artist:    return "Your ride-or-die artist?"
        case .hated:     return "Any genres you can't stand?"
        case .rainy:     return "What's your rainy day soundtrack?"
        case .workout:   return "What powers your workout?"
        case .decade:    return "What decade speaks to you?"
        case .listening: return "How do you listen?"
        case .age:       return "What's your age range?"
        case .location:  return "Where are you located?"
        case .connect:   return "You're almost there!"
        }
    }

    var subtitle: String {
        switch self {
        case .genres:    return "These help us understand your musical identity"
        case .artist:    return "That one artist you'll defend to the end"
        case .hated:     return "We'll make sure to avoid these"
        case .rainy:     return "When the mood is mellow"
        case .workout:   return "Your energy anthem"
        case .decade:    return "The era that shaped your taste"
        case .listening: return "Everyone has their style"
        case .age:       return "Helps us personalize your experience"
        case .location:  return "We'll place you on the Juke World map"
        case .connect:   return "Connect Spotify to complete your profile"
        }
    }

    var isRequired: Bool {
        self == .genres
    }
}

// MARK: - Genre

struct OnboardingGenre: Codable, Identifiable {
    let id: String
    let name: String
    let spotifyId: String
    let topArtists: [GenreArtist]

    enum CodingKeys: String, CodingKey {
        case id, name
        case spotifyId = "spotify_id"
        case topArtists = "top_artists"
    }
}

struct GenreArtist: Codable {
    let name: String
    let imageUrl: String

    enum CodingKeys: String, CodingKey {
        case name
        case imageUrl = "image_url"
    }
}

// MARK: - Artist (search result)

struct OnboardingArtist: Codable, Identifiable {
    let id: String
    let name: String
    let spotifyId: String
    let imageUrl: String
    let genres: [String]

    enum CodingKeys: String, CodingKey {
        case id, name, genres
        case spotifyId = "spotify_id"
        case imageUrl = "image_url"
    }
}

// MARK: - City

struct CityLocation: Codable, Identifiable {
    let name: String
    let country: String
    let lat: Double
    let lng: Double

    var id: String { "\(name)-\(country)" }
}

// MARK: - Mood / Vibe options

struct MoodOption: Identifiable {
    let id: String
    let label: String
    let icon: String
}

struct WorkoutVibe: Identifiable {
    let id: String
    let label: String
    let icon: String
    let description: String
}

struct DecadeOption: Identifiable {
    let id: String
    let label: String
    let vibe: String
}

// MARK: - Preset data (mirrors web onboardingApi.ts)

let FEATURED_GENRES: [OnboardingGenre] = [
    OnboardingGenre(id: "hiphop",    name: "Hip-Hop",    spotifyId: "hip-hop",    topArtists: [GenreArtist(name: "Drake", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb4293385d324db8558179afd9"), GenreArtist(name: "Kendrick Lamar", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb52696c89a9a2d7ed21d73e92"), GenreArtist(name: "J. Cole", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb078456da9d0b07fd2b0c3eba")]),
    OnboardingGenre(id: "rock",      name: "Rock",       spotifyId: "rock",       topArtists: [GenreArtist(name: "Foo Fighters", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb9a43b87b50cd3d03544bb3e5"), GenreArtist(name: "Green Day", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb4b2a1d9ef4e6c16e5cbe8e3e"), GenreArtist(name: "Nirvana", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb7bbad89a61061304ec842588")]),
    OnboardingGenre(id: "pop",       name: "Pop",        spotifyId: "pop",        topArtists: [GenreArtist(name: "Taylor Swift", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb5a00969a4698c3132a15fbb0"), GenreArtist(name: "Dua Lipa", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb1bbee4a02f85ecc58d385c3e"), GenreArtist(name: "The Weeknd", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb214f3cf1cbe7139c1e26ffbb")]),
    OnboardingGenre(id: "rnb",       name: "R&B",        spotifyId: "r-n-b",      topArtists: [GenreArtist(name: "SZA", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb0895066d172e1f51f520bc65"), GenreArtist(name: "Frank Ocean", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb7b2a499c1df8cf0ab8ee9722"), GenreArtist(name: "Daniel Caesar", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb94a251170e5bc6c5cc67385a")]),
    OnboardingGenre(id: "electronic", name: "Electronic", spotifyId: "electronic", topArtists: [GenreArtist(name: "Daft Punk", imageUrl: "https://i.scdn.co/image/ab6761610000e5eba7bfd7835b5c1eee0c95fa6e"), GenreArtist(name: "Calvin Harris", imageUrl: "https://i.scdn.co/image/ab6761610000e5ebf150017ca69c8793503c2d4f"), GenreArtist(name: "Disclosure", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb855d1cdf330080d9dafcc825")]),
    OnboardingGenre(id: "country",   name: "Country",    spotifyId: "country",    topArtists: [GenreArtist(name: "Morgan Wallen", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb21ed0100a3a4e5aa3c57f6dd"), GenreArtist(name: "Luke Combs", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb5db6179a702a931368a1b2c2"), GenreArtist(name: "Chris Stapleton", imageUrl: "https://i.scdn.co/image/ab6761610000e5ebce5c7a49d8694e0d99e974ee")]),
    OnboardingGenre(id: "jazz",      name: "Jazz",       spotifyId: "jazz",       topArtists: [GenreArtist(name: "Kamasi Washington", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb717a36763ed9c9e9ed4c6d49"), GenreArtist(name: "Robert Glasper", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb6d922ec4c474c0200f0c5655"), GenreArtist(name: "Esperanza Spalding", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb8cbf3b45d3c2ca98c35f4e3f")]),
    OnboardingGenre(id: "classical", name: "Classical",  spotifyId: "classical",  topArtists: [GenreArtist(name: "Yo-Yo Ma", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb36a5ffce3db2c3c0a7a8b67f"), GenreArtist(name: "Lang Lang", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb7f4c7c12d8c9c5f9f5db0dc8"), GenreArtist(name: "Hilary Hahn", imageUrl: "https://i.scdn.co/image/ab6761610000e5ebc8e7e4c2f0c85a6f2c6c2a47")]),
    OnboardingGenre(id: "latin",     name: "Latin",      spotifyId: "latin",      topArtists: [GenreArtist(name: "Bad Bunny", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb9ad50e478a469c5f4d974426"), GenreArtist(name: "J Balvin", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb5e787f6c1d56e97b0c6e68c6"), GenreArtist(name: "Rosalía", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb30c6f97f0a269a02c87bb95e")]),
    OnboardingGenre(id: "indie",     name: "Indie",      spotifyId: "indie",      topArtists: [GenreArtist(name: "Tame Impala", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb5765c90bb5ef3a86f7cb980d"), GenreArtist(name: "Arctic Monkeys", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb7da39dea0a72f581535fb11f"), GenreArtist(name: "Mac DeMarco", imageUrl: "https://i.scdn.co/image/ab6761610000e5eb922e58b75ed5d8c7f4eb8f73")]),
]

let RAINY_DAY_MOODS: [MoodOption] = [
    MoodOption(id: "mellow",   label: "Mellow & Acoustic",    icon: "🌧️"),
    MoodOption(id: "jazz",     label: "Jazz & Lo-fi",          icon: "☕"),
    MoodOption(id: "indie",    label: "Indie & Chill",         icon: "🌿"),
    MoodOption(id: "classical",label: "Classical & Ambient",   icon: "🎻"),
    MoodOption(id: "rnb",      label: "R&B & Soul",            icon: "💜"),
]

let WORKOUT_VIBES: [WorkoutVibe] = [
    WorkoutVibe(id: "intense", label: "Maximum Intensity", icon: "🔥", description: "Heavy bass, fast tempo"),
    WorkoutVibe(id: "hiphop",  label: "Hip-Hop Energy",    icon: "💪", description: "Beats that hit hard"),
    WorkoutVibe(id: "rock",    label: "Rock Power",        icon: "🎸", description: "Guitar-driven adrenaline"),
    WorkoutVibe(id: "edm",     label: "EDM Drops",         icon: "⚡", description: "Build-ups and releases"),
    WorkoutVibe(id: "pop",     label: "Pop Anthems",       icon: "🎤", description: "Sing-along motivation"),
]

let DECADES: [DecadeOption] = [
    DecadeOption(id: "60s",   label: "60s",   vibe: "Psychedelic & Soul"),
    DecadeOption(id: "70s",   label: "70s",   vibe: "Disco & Punk"),
    DecadeOption(id: "80s",   label: "80s",   vibe: "Synth & New Wave"),
    DecadeOption(id: "90s",   label: "90s",   vibe: "Grunge & Golden Era"),
    DecadeOption(id: "2000s", label: "2000s", vibe: "Pop Punk & Crunk"),
    DecadeOption(id: "2010s", label: "2010s", vibe: "EDM & Streaming"),
    DecadeOption(id: "2020s", label: "2020s", vibe: "Hyperpop & Revival"),
]

let AGE_RANGES: [String] = ["18-24", "25-34", "35-44", "45-54", "55+"]

let CITIES: [CityLocation] = [
    CityLocation(name: "New York",     country: "USA",         lat: 40.71,  lng: -74.01),
    CityLocation(name: "Los Angeles",  country: "USA",         lat: 34.05,  lng: -118.24),
    CityLocation(name: "Chicago",      country: "USA",         lat: 41.88,  lng: -87.63),
    CityLocation(name: "Houston",      country: "USA",         lat: 29.76,  lng: -95.37),
    CityLocation(name: "Phoenix",      country: "USA",         lat: 33.45,  lng: -112.07),
    CityLocation(name: "London",       country: "UK",          lat: 51.51,  lng: -0.13),
    CityLocation(name: "Paris",        country: "France",      lat: 48.86,  lng: 2.35),
    CityLocation(name: "Tokyo",        country: "Japan",       lat: 35.68,  lng: 139.69),
    CityLocation(name: "Sydney",       country: "Australia",   lat: -33.87, lng: 151.21),
    CityLocation(name: "Toronto",      country: "Canada",      lat: 43.65,  lng: -79.38),
    CityLocation(name: "Berlin",       country: "Germany",     lat: 52.52,  lng: 13.41),
    CityLocation(name: "Amsterdam",    country: "Netherlands", lat: 52.37,  lng: 4.90),
    CityLocation(name: "Seoul",        country: "South Korea", lat: 37.57,  lng: 126.98),
    CityLocation(name: "Singapore",    country: "Singapore",   lat: 1.35,   lng: 103.82),
    CityLocation(name: "Dubai",        country: "UAE",         lat: 25.20,  lng: 55.27),
    CityLocation(name: "Mumbai",       country: "India",       lat: 19.08,  lng: 72.88),
    CityLocation(name: "São Paulo",    country: "Brazil",      lat: -23.55, lng: -46.63),
    CityLocation(name: "Mexico City",  country: "Mexico",      lat: 19.43,  lng: -99.13),
    CityLocation(name: "Lagos",        country: "Nigeria",     lat: 6.52,   lng: 3.38),
    CityLocation(name: "Cairo",        country: "Egypt",       lat: 30.04,  lng: 31.24),
    CityLocation(name: "Austin",       country: "USA",         lat: 30.27,  lng: -97.74),
    CityLocation(name: "Nashville",    country: "USA",         lat: 36.16,  lng: -86.78),
    CityLocation(name: "Atlanta",      country: "USA",         lat: 33.75,  lng: -84.39),
    CityLocation(name: "Miami",        country: "USA",         lat: 25.76,  lng: -80.19),
    CityLocation(name: "Seattle",      country: "USA",         lat: 47.61,  lng: -122.33),
    CityLocation(name: "San Francisco",country: "USA",         lat: 37.77,  lng: -122.42),
    CityLocation(name: "Denver",       country: "USA",         lat: 39.74,  lng: -104.99),
    CityLocation(name: "Boston",       country: "USA",         lat: 42.36,  lng: -71.06),
    CityLocation(name: "Philadelphia", country: "USA",         lat: 39.95,  lng: -75.17),
    CityLocation(name: "Detroit",      country: "USA",         lat: 42.33,  lng: -83.05),
]

// MARK: - Onboarding data (persisted)

struct OnboardingData: Codable {
    var favoriteGenres: [String] = []
    var rideOrDieArtist: OnboardingArtist? = nil
    var hatedGenres: [String] = []
    var rainyDayMood: String? = nil
    var workoutVibe: String? = nil
    var favoriteDecade: String? = nil
    var listeningStyle: String? = nil   // "playlist" | "album"
    var ageRange: String? = nil
    var location: CityLocation? = nil
    var spotifyConnected: Bool = false
    var completedAt: String? = nil
}

func searchCities(_ query: String) -> [CityLocation] {
    let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    guard !trimmed.isEmpty else { return [] }
    return CITIES.filter {
        $0.name.lowercased().contains(trimmed) || $0.country.lowercased().contains(trimmed)
    }.prefix(10).map { $0 }
}
