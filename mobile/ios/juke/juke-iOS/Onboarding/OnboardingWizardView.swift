import SwiftUI

struct OnboardingWizardView: View {
    @EnvironmentObject private var session: SessionStore
    @StateObject private var store: OnboardingStore
    @Binding var navigateToWorld: Bool
    @Binding var worldFocus: WorldFocus?
    @State private var featuredGenres: [OnboardingGenre] = []
    @State private var isLoadingGenres = false
    @State private var genreError: String?

    private let genreService = OnboardingService()

    init(userKey: String? = nil, navigateToWorld: Binding<Bool>, worldFocus: Binding<WorldFocus?>) {
        _store = StateObject(wrappedValue: OnboardingStore(userKey: userKey))
        _navigateToWorld = navigateToWorld
        _worldFocus = worldFocus
    }

    var body: some View {
        NavigationStack {
            ZStack {
                JukeBackground()
                VStack(spacing: 0) {
                    progressBar
                    stepContent
                }
            }
            .toolbar(.hidden, for: .navigationBar)
        }
        .task(id: session.token) {
            await loadFeaturedGenres()
        }
    }

    // MARK: - Progress bar

    private var progressBar: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Rectangle()
                    .fill(JukePalette.panel)
                    .frame(height: 3)
                Rectangle()
                    .fill(JukePalette.accent)
                    .frame(width: geo.size.width * store.progress / 100, height: 3)
                    .animation(.easeInOut(duration: 0.3), value: store.progress)
            }
        }
        .frame(height: 3)
    }

    // MARK: - Step routing

    private var stepContent: some View {
        ScrollView(showsIndicators: false) {
            VStack(spacing: 24) {
                stepHeader
                switch store.currentStep {
                case .genres:    GenreStepView(store: store, genres: featuredGenres, isLoading: isLoadingGenres, error: genreError)
                case .artist:    ArtistStepView(store: store, session: session)
                case .hated:     HatedGenresStepView(store: store, genres: featuredGenres, isLoading: isLoadingGenres, error: genreError)
                case .rainy:     MoodStepView(store: store, options: RAINY_DAY_MOODS, selected: store.data.rainyDayMood) { store.setRainyDayMood($0) }
                case .workout:   WorkoutStepView(store: store)
                case .decade:    DecadeStepView(store: store)
                case .listening: ListeningStyleStepView(store: store)
                case .age:       AgeRangeStepView(store: store)
                case .location:  LocationStepView(store: store)
                case .connect:   ConnectStepView(store: store, session: session, navigateToWorld: $navigateToWorld, worldFocus: $worldFocus)
                }
                stepFooter
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 32)
        }
    }

    // MARK: - Header (step label + title + subtitle + back/restart)

    private var stepHeader: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                if store.canGoBack && store.currentStep != .connect {
                    Button(action: store.goBack) {
                        Image(systemName: "arrow.left")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundColor(JukePalette.text)
                    }
                    .buttonStyle(.plain)
                }
                Spacer()
                Button(action: store.restart) {
                    Image(systemName: "arrow.counterclockwise")
                        .font(.system(size: 16))
                        .foregroundColor(JukePalette.muted)
                }
                .buttonStyle(.plain)
            }

            Text("Step \(store.currentStepIndex + 1) of \(store.totalSteps)")
                .font(.caption)
                .foregroundColor(JukePalette.muted)
                .textCase(.uppercase)
                .kerning(1.2)

            Text(store.currentStep.title)
                .font(.title.bold())
                .foregroundColor(JukePalette.text)
                .fixedSize(horizontal: false, vertical: true)

            Text(store.currentStep.subtitle)
                .font(.subheadline)
                .foregroundColor(JukePalette.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - Footer (Skip / Continue)

    private var stepFooter: some View {
        HStack(spacing: 12) {
            if !store.currentStep.isRequired && store.currentStep != .connect {
                Button("Skip") { store.goNext() }
                    .buttonStyle(JukeButtonStyle(variant: .ghost))
                    .frame(maxWidth: .infinity)
            }
            if store.currentStep != .connect {
                Button("Continue") { store.goNext() }
                    .buttonStyle(JukeButtonStyle())
                    .frame(maxWidth: .infinity)
                    .disabled(store.currentStep == .genres && store.data.favoriteGenres.isEmpty)
                    .opacity(store.currentStep == .genres && store.data.favoriteGenres.isEmpty ? 0.5 : 1)
            }
        }
    }

    private func loadFeaturedGenres() async {
        guard let token = session.token else {
            featuredGenres = []
            return
        }
        isLoadingGenres = true
        genreError = nil
        do {
            let data = try await genreService.fetchFeaturedGenres(token: token)
            featuredGenres = data
        } catch {
            featuredGenres = []
            genreError = error.localizedDescription
        }
        isLoadingGenres = false
    }
}

// MARK: - Genre Step

struct GenreStepView: View {
    @ObservedObject var store: OnboardingStore
    let genres: [OnboardingGenre]
    let isLoading: Bool
    let error: String?

    var body: some View {
        VStack(spacing: 16) {
            if isLoading {
                JukeSpinner()
            } else if let error, !error.isEmpty {
                JukeStatusBanner(message: error, variant: .error)
            }

            let displayGenres = genres.isEmpty ? FEATURED_GENRES : genres
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 12)], spacing: 12) {
                ForEach(displayGenres) { genre in
                    let isSelected = store.data.favoriteGenres.contains(genre.id)
                    let isDisabled = store.data.favoriteGenres.count >= 3 && !isSelected

                    Button(action: { store.toggleFavoriteGenre(genre.id) }) {
                        VStack(spacing: 8) {
                            HStack(spacing: -12) {
                                ForEach(genre.topArtists.prefix(3), id: \.name) { artist in
                                    if let url = URL(string: artist.imageUrl) {
                                        AsyncImage(url: url) { img in
                                            img.resizable().aspectRatio(contentMode: .fill)
                                                .frame(width: 36, height: 36)
                                                .clipShape(Circle())
                                        } placeholder: {
                                            Circle().fill(JukePalette.panel).frame(width: 36, height: 36)
                                        }
                                    }
                                }
                            }
                            Text(genre.name)
                                .font(.subheadline.bold())
                                .foregroundColor(isSelected ? JukePalette.accent : JukePalette.text)
                            Text(genre.topArtists.map { $0.name }.joined(separator: ", "))
                                .font(.caption2)
                                .foregroundColor(JukePalette.muted)
                                .lineLimit(2)
                                .multilineTextAlignment(.center)
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity)
                        .background(
                            RoundedRectangle(cornerRadius: 16)
                                .fill(isSelected ? JukePalette.accent.opacity(0.15) : JukePalette.panel)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 16)
                                .stroke(isSelected ? JukePalette.accent : JukePalette.border, lineWidth: 1)
                        )
                        .overlay(alignment: .topTrailing) {
                            if isSelected {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundColor(JukePalette.accent)
                                    .font(.system(size: 16))
                                    .padding(4)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(isDisabled)
                    .opacity(isDisabled ? 0.4 : 1)
                }
            }
            Text("\(store.data.favoriteGenres.count)/3 selected")
                .font(.caption)
                .foregroundColor(JukePalette.muted)
                .frame(maxWidth: .infinity)
        }
    }
}

// MARK: - Artist Step

struct ArtistStepView: View {
    @ObservedObject var store: OnboardingStore
    let session: SessionStore

    @State private var query = ""
    @State private var results: [OnboardingArtist] = []
    @State private var isSearching = false
    @State private var showResults = false
    @State private var errorMessage: String?

    private let service = OnboardingService()

    var body: some View {
        VStack(spacing: 16) {
            if let artist = store.data.rideOrDieArtist {
                selectedArtist(artist)
            } else {
                searchSurface
            }
        }
    }

    private func selectedArtist(_ artist: OnboardingArtist) -> some View {
        JukeCard {
            HStack(spacing: 16) {
                if let url = URL(string: artist.imageUrl), !artist.imageUrl.isEmpty {
                    AsyncImage(url: url) { img in
                        img.resizable().aspectRatio(contentMode: .fill)
                            .frame(width: 64, height: 64)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                    } placeholder: {
                        RoundedRectangle(cornerRadius: 12).fill(JukePalette.panel).frame(width: 64, height: 64)
                    }
                } else {
                    RoundedRectangle(cornerRadius: 12).fill(JukePalette.panel).frame(width: 64, height: 64)
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text(artist.name)
                        .font(.headline)
                        .foregroundColor(JukePalette.text)
                    Text("Your ride-or-die")
                        .font(.subheadline)
                        .foregroundColor(JukePalette.muted)
                }
                Spacer()
                Button(action: { store.setRideOrDieArtist(nil) }) {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(JukePalette.muted)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var searchSurface: some View {
        VStack(spacing: 12) {
            JukeInputField(
                label: "Search Artist",
                placeholder: "Search for an artist…",
                text: $query,
                keyboard: .default
            )
            .onChange(of: query) { _, newValue in
                debounceSearch(newValue)
            }

            if showResults {
                if isSearching {
                    Text("Searching…")
                        .font(.subheadline)
                        .foregroundColor(JukePalette.muted)
                } else if let errorMessage, !errorMessage.isEmpty {
                    Text(errorMessage)
                        .font(.subheadline)
                        .foregroundColor(JukePalette.warning)
                } else if !results.isEmpty {
                    VStack(spacing: 0) {
                        ForEach(results) { artist in
                            Button(action: { selectArtist(artist) }) {
                                HStack(spacing: 12) {
                                    if let url = URL(string: artist.imageUrl), !artist.imageUrl.isEmpty {
                                        AsyncImage(url: url) { img in
                                            img.resizable().aspectRatio(contentMode: .fill)
                                                .frame(width: 40, height: 40)
                                                .clipShape(Circle())
                                        } placeholder: {
                                            Circle().fill(JukePalette.panel).frame(width: 40, height: 40)
                                        }
                                    } else {
                                        Circle().fill(JukePalette.panel).frame(width: 40, height: 40)
                                    }
                                    Text(artist.name)
                                        .font(.subheadline)
                                        .foregroundColor(JukePalette.text)
                                    Spacer()
                                }
                                .padding(.vertical, 10)
                            }
                            .buttonStyle(.plain)
                            Divider().padding(.leading, 52)
                        }
                    }
                    .background(RoundedRectangle(cornerRadius: 12).fill(JukePalette.panel))
                } else if !query.trimmingCharacters(in: .whitespaces).isEmpty {
                    Text("No artists found")
                        .font(.subheadline)
                        .foregroundColor(JukePalette.muted)
                }
            }
        }
    }

    private func debounceSearch(_ value: String) {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            results = []
            showResults = false
            return
        }
        Task {
            isSearching = true
            showResults = true
            errorMessage = nil
            guard let token = session.token else {
                isSearching = false
                errorMessage = "You're signed out. Please log in again."
                return
            }
            do {
                let data = try await service.searchArtists(query: trimmed, token: token)
                results = data
            } catch {
                results = []
                errorMessage = error.localizedDescription
            }
            isSearching = false
        }
    }

    private func selectArtist(_ artist: OnboardingArtist) {
        store.setRideOrDieArtist(artist)
        query = ""
        showResults = false
    }
}

// MARK: - Hated Genres Step

struct HatedGenresStepView: View {
    @ObservedObject var store: OnboardingStore
    let genres: [OnboardingGenre]
    let isLoading: Bool
    let error: String?

    private var availableGenres: [OnboardingGenre] {
        let source = genres.isEmpty ? FEATURED_GENRES : genres
        return source.filter { !store.data.favoriteGenres.contains($0.id) }
    }

    var body: some View {
        VStack(spacing: 16) {
            if isLoading {
                JukeSpinner()
            } else if let error, !error.isEmpty {
                JukeStatusBanner(message: error, variant: .error)
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 12)], spacing: 12) {
                ForEach(availableGenres) { genre in
                    let isSelected = store.data.hatedGenres.contains(genre.id)
                    let isDisabled = store.data.hatedGenres.count >= 3 && !isSelected

                    Button(action: { store.toggleHatedGenre(genre.id) }) {
                        VStack(spacing: 8) {
                            Text(genre.name)
                                .font(.subheadline.bold())
                                .foregroundColor(isSelected ? JukePalette.accent : JukePalette.text)
                            Text(genre.topArtists.map { $0.name }.joined(separator: ", "))
                                .font(.caption2)
                                .foregroundColor(JukePalette.muted)
                                .lineLimit(2)
                                .multilineTextAlignment(.center)
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity)
                        .background(
                            RoundedRectangle(cornerRadius: 16)
                                .fill(isSelected ? JukePalette.accent.opacity(0.15) : JukePalette.panel)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 16)
                                .stroke(isSelected ? JukePalette.accent : JukePalette.border, lineWidth: 1)
                        )
                        .overlay(alignment: .topTrailing) {
                            if isSelected {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundColor(JukePalette.accent)
                                    .font(.system(size: 16))
                                    .padding(4)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(isDisabled)
                    .opacity(isDisabled ? 0.4 : 1)
                }
            }
            Text("\(store.data.hatedGenres.count)/3 selected (optional)")
                .font(.caption)
                .foregroundColor(JukePalette.muted)
                .frame(maxWidth: .infinity)
        }
    }
}

// MARK: - Mood Step (Rainy Day)

struct MoodStepView: View {
    @ObservedObject var store: OnboardingStore
    let options: [MoodOption]
    let selected: String?
    let onSelect: (String?) -> Void

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 12)], spacing: 12) {
            ForEach(options) { option in
                let isSelected = selected == option.id
                Button(action: { onSelect(isSelected ? nil : option.id) }) {
                    VStack(spacing: 8) {
                        Text(option.icon)
                            .font(.system(size: 28))
                        Text(option.label)
                            .font(.subheadline.bold())
                            .foregroundColor(isSelected ? JukePalette.accent : JukePalette.text)
                            .multilineTextAlignment(.center)
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity)
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .fill(isSelected ? JukePalette.accent.opacity(0.15) : JukePalette.panel)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .stroke(isSelected ? JukePalette.accent : JukePalette.border, lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)
            }
        }
    }
}

// MARK: - Workout Step

struct WorkoutStepView: View {
    @ObservedObject var store: OnboardingStore

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 12)], spacing: 12) {
            ForEach(WORKOUT_VIBES) { vibe in
                let isSelected = store.data.workoutVibe == vibe.id
                Button(action: { store.setWorkoutVibe(isSelected ? nil : vibe.id) }) {
                    VStack(spacing: 8) {
                        Text(vibe.icon)
                            .font(.system(size: 28))
                        Text(vibe.label)
                            .font(.subheadline.bold())
                            .foregroundColor(isSelected ? JukePalette.accent : JukePalette.text)
                            .multilineTextAlignment(.center)
                        Text(vibe.description)
                            .font(.caption)
                            .foregroundColor(JukePalette.muted)
                            .multilineTextAlignment(.center)
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity)
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .fill(isSelected ? JukePalette.accent.opacity(0.15) : JukePalette.panel)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .stroke(isSelected ? JukePalette.accent : JukePalette.border, lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)
            }
        }
    }
}

// MARK: - Decade Step

struct DecadeStepView: View {
    @ObservedObject var store: OnboardingStore

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 100), spacing: 10)], spacing: 10) {
            ForEach(DECADES) { decade in
                let isSelected = store.data.favoriteDecade == decade.id
                Button(action: { store.setFavoriteDecade(isSelected ? nil : decade.id) }) {
                    VStack(spacing: 4) {
                        Text(decade.label)
                            .font(.headline.bold())
                            .foregroundColor(isSelected ? JukePalette.accent : JukePalette.text)
                        Text(decade.vibe)
                            .font(.caption)
                            .foregroundColor(JukePalette.muted)
                            .multilineTextAlignment(.center)
                    }
                    .padding(12)
                    .frame(maxWidth: .infinity)
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .fill(isSelected ? JukePalette.accent.opacity(0.15) : JukePalette.panel)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .stroke(isSelected ? JukePalette.accent : JukePalette.border, lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)
            }
        }
    }
}

// MARK: - Listening Style Step

struct ListeningStyleStepView: View {
    @ObservedObject var store: OnboardingStore

    var body: some View {
        HStack(spacing: 12) {
            styleCard(id: "playlist", icon: "🔀", title: "Playlist Person", desc: "Curated vibes, shuffle on, discover new tracks")
            styleCard(id: "album",    icon: "💿", title: "Album Listener",  desc: "Front to back, the way it was meant to be heard")
        }
    }

    private func styleCard(id: String, icon: String, title: String, desc: String) -> some View {
        let isSelected = store.data.listeningStyle == id
        return Button(action: { store.setListeningStyle(isSelected ? nil : id) }) {
            VStack(spacing: 10) {
                Text(icon)
                    .font(.system(size: 32))
                Text(title)
                    .font(.subheadline.bold())
                    .foregroundColor(isSelected ? JukePalette.accent : JukePalette.text)
                Text(desc)
                    .font(.caption)
                    .foregroundColor(JukePalette.muted)
                    .multilineTextAlignment(.center)
            }
            .padding(16)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 16)
                    .fill(isSelected ? JukePalette.accent.opacity(0.15) : JukePalette.panel)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(isSelected ? JukePalette.accent : JukePalette.border, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Age Range Step

struct AgeRangeStepView: View {
    @ObservedObject var store: OnboardingStore

    var body: some View {
        HStack(spacing: 10) {
            ForEach(AGE_RANGES, id: \.self) { range in
                let isSelected = store.data.ageRange == range
                Button(action: { store.setAgeRange(isSelected ? nil : range) }) {
                    Text(range)
                        .font(.subheadline.bold())
                        .foregroundColor(isSelected ? JukePalette.accent : JukePalette.text)
                        .padding(.vertical, 10)
                        .padding(.horizontal, 16)
                        .background(
                            Capsule()
                                .fill(isSelected ? JukePalette.accent.opacity(0.15) : JukePalette.panel)
                        )
                        .overlay(
                            Capsule()
                                .stroke(isSelected ? JukePalette.accent : JukePalette.border, lineWidth: 1)
                        )
                }
                .buttonStyle(.plain)
            }
        }
        .frame(maxWidth: .infinity, alignment: .center)
    }
}

// MARK: - Location Step

struct LocationStepView: View {
    @ObservedObject var store: OnboardingStore

    @State private var query = ""
    @State private var results: [CityLocation] = []
    @State private var showResults = false

    var body: some View {
        VStack(spacing: 16) {
            if let city = store.data.location {
                selectedLocation(city)
            } else {
                searchSurface
            }
        }
    }

    private func selectedLocation(_ city: CityLocation) -> some View {
        JukeCard {
            HStack(spacing: 16) {
                Image(systemName: "mappin.and.ellipse")
                    .font(.system(size: 28))
                    .foregroundColor(JukePalette.accent)
                VStack(alignment: .leading, spacing: 4) {
                    Text(city.name)
                        .font(.headline)
                        .foregroundColor(JukePalette.text)
                    Text(city.country)
                        .font(.subheadline)
                        .foregroundColor(JukePalette.muted)
                }
                Spacer()
                Button(action: { store.setLocation(nil) }) {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(JukePalette.muted)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var searchSurface: some View {
        VStack(spacing: 12) {
            JukeInputField(
                label: "City",
                placeholder: "Search for your city…",
                text: $query,
                keyboard: .default
            )
            .onChange(of: query) { _, newValue in
                let trimmed = newValue.trimmingCharacters(in: .whitespacesAndNewlines)
                if trimmed.isEmpty {
                    results = []
                    showResults = false
                } else {
                    results = searchCities(trimmed)
                    showResults = !results.isEmpty
                }
            }

            if showResults && !results.isEmpty {
                VStack(spacing: 0) {
                    ForEach(results) { city in
                        Button(action: { selectCity(city) }) {
                            HStack(spacing: 12) {
                                Image(systemName: "mappin")
                                    .foregroundColor(JukePalette.accent)
                                    .font(.system(size: 16))
                                Text("\(city.name), \(city.country)")
                                    .font(.subheadline)
                                    .foregroundColor(JukePalette.text)
                                Spacer()
                            }
                            .padding(.vertical, 12)
                        }
                        .buttonStyle(.plain)
                        Divider()
                    }
                }
                .background(RoundedRectangle(cornerRadius: 12).fill(JukePalette.panel))
            }
        }
    }

    private func selectCity(_ city: CityLocation) {
        store.setLocation(city)
        query = ""
        showResults = false
    }
}

// MARK: - Connect / Summary Step

struct ConnectStepView: View {
    @ObservedObject var store: OnboardingStore
    let session: SessionStore
    @Binding var navigateToWorld: Bool
    @Binding var worldFocus: WorldFocus?

    @State private var isSaving = false
    @State private var error: String?

    private let service = OnboardingService()

    var body: some View {
        VStack(spacing: 24) {
            // Completion icon
            Image(systemName: "checkmark.circle")
                .font(.system(size: 64))
                .foregroundColor(JukePalette.accent)

            // Summary
            JukeCard {
                VStack(alignment: .leading, spacing: 12) {
                    summaryRow(label: "Genres", value: "\(store.data.favoriteGenres.count) selected")
                    if let artist = store.data.rideOrDieArtist {
                        summaryRow(label: "Ride-or-Die", value: artist.name)
                    }
                    if let decade = store.data.favoriteDecade {
                        summaryRow(label: "Era", value: decade)
                    }
                    if let style = store.data.listeningStyle {
                        summaryRow(label: "Style", value: style == "playlist" ? "Playlist" : "Album")
                    }
                    if let city = store.data.location {
                        summaryRow(label: "Location", value: city.name)
                    }
                }
            }

            if let error {
                JukeStatusBanner(message: error, variant: .error)
            }

            // Action buttons
            VStack(spacing: 12) {
                Button(action: { saveAndFinish(connectSpotify: false) }) {
                    if isSaving {
                        HStack {
                            Spacer()
                            JukeSpinner()
                            Spacer()
                        }
                    } else {
                        Text("Enter Juke World")
                            .fontWeight(.semibold)
                    }
                }
                .buttonStyle(JukeButtonStyle())
                .disabled(isSaving)

                Button(action: { saveAndFinish(connectSpotify: true) }) {
                    Text("Connect Spotify & Enter Juke World")
                        .font(.subheadline)
                        .foregroundColor(JukePalette.accent)
                }
                .buttonStyle(.plain)
                .disabled(isSaving)
            }
        }
    }

    private func summaryRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.subheadline)
                .foregroundColor(JukePalette.muted)
            Spacer()
            Text(value)
                .font(.subheadline.bold())
                .foregroundColor(JukePalette.text)
        }
    }

    private func saveAndFinish(connectSpotify: Bool) {
        isSaving = true
        error = nil

        Task {
            guard let token = session.token else {
                error = "Session expired. Please sign in again."
                isSaving = false
                return
            }

            do {
                try await service.saveProfile(data: store.data, token: token)
                store.clearDraft()
                try? await session.refreshProfile()
                if let city = store.data.location {
                    worldFocus = WorldFocus(
                        lat: city.lat,
                        lng: city.lng,
                        username: session.username ?? session.profile?.username
                    )
                } else {
                    worldFocus = nil
                }
                navigateToWorld = true
            } catch {
                self.error = error.localizedDescription
                isSaving = false
                return
            }

            isSaving = false
            // ContentView will re-route once onboarding is marked complete
        }
    }
}

#Preview {
    OnboardingWizardView(userKey: nil, navigateToWorld: .constant(false), worldFocus: .constant(nil))
        .environmentObject(SessionStore())
}
