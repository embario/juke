import SwiftUI

struct SearchDashboardView: View {
    @EnvironmentObject private var session: SessionStore
    @StateObject private var viewModel: SearchViewModel
    @State private var activeScopes: Set<SearchScope> = Set(SearchScope.allCases)

    init(session: SessionStore) {
        _viewModel = StateObject(wrappedValue: SearchViewModel(session: session))
    }

    var body: some View {
        NavigationStack {
            ZStack(alignment: .bottom) {
                VStack(spacing: 0) {
                    JukeBackground()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .overlay(alignment: .top) {
                            ScrollView(showsIndicators: false) {
                                VStack(spacing: 24) {
                                    heroCard
                                    searchSurface
                                    if viewModel.isLoading {
                                        JukeCard {
                                            HStack(spacing: 12) {
                                                JukeSpinner()
                                                Text("Cranking up the signal…")
                                                    .foregroundColor(JukePalette.muted)
                                                Spacer()
                                            }
                                        }
                                    }
                                    JukeStatusBanner(message: viewModel.errorMessage, variant: .error)
                                    resultsStack
                                }
                                .padding(.horizontal, 24)
                                .padding(.vertical, 32)
                                .padding(.bottom, 64)
                            }
                        }
                }
                PlaybackBarView(session: session)
            }
            .navigationTitle("Discover")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    NavigationLink {
                        JukeWorldView()
                    } label: {
                        Label("Juke World", systemImage: "globe")
                            .tint(JukePalette.accent)
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Log Out", action: session.logout)
                        .tint(JukePalette.accent)
                }
            }
        }
    }

    private var heroCard: some View {
        JukeCard {
            VStack(alignment: .leading, spacing: 12) {
                Text("Hey, \(session.profile?.preferredName ?? "Juke listener")")
                    .font(.title.bold())
                    .foregroundColor(JukePalette.text)
                Text(session.profile?.tagline.isEmpty == false ? (session.profile?.tagline ?? "") : "Ready to find new sonic obsessions?")
                    .foregroundColor(JukePalette.muted)
                HStack(spacing: 10) {
                    Label("Live catalog", systemImage: "waveform")
                        .font(.caption)
                        .padding(.vertical, 6)
                        .padding(.horizontal, 14)
                        .background(
                            Capsule()
                                .fill(JukePalette.accent.opacity(0.15))
                        )
                        .foregroundColor(JukePalette.accent)
                    Spacer(minLength: 0)
                }
            }
        }
    }

    private var searchSurface: some View {
        JukeCard {
            VStack(alignment: .leading, spacing: 16) {
                Text("Global Search")
                    .font(.headline)
                    .foregroundColor(JukePalette.text)
                Text("Scan the entire catalog without leaving native. Filter the feeds to zero in on exactly what you need.")
                    .font(.subheadline)
                    .foregroundColor(JukePalette.muted)
                VStack(spacing: 12) {
                    JukeInputField(
                        label: "Query",
                        placeholder: "Search profiles, artists, albums, tracks",
                        text: $viewModel.query
                    )
                    Button(action: viewModel.performSearch) {
                        Label("Search", systemImage: "magnifyingglass")
                            .fontWeight(.semibold)
                    }
                    .buttonStyle(JukeButtonStyle())
                    .disabled(viewModel.query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .opacity(viewModel.query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? 0.6 : 1)
                }
                scopeSelector
            }
        }
        .onSubmit(of: .text) {
            viewModel.performSearch()
        }
    }

    private var scopeSelector: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Show results for")
                .font(.caption)
                .foregroundColor(JukePalette.muted)
                .textCase(.uppercase)
                .kerning(1.5)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 12)], spacing: 12) {
                ForEach(SearchScope.allCases) { scope in
                    JukeChip(label: scope.title, isActive: activeScopes.contains(scope)) {
                        toggle(scope)
                    }
                }
            }
        }
    }

    private var resultsStack: some View {
        VStack(spacing: 20) {
            if shouldShowEmptyState {
                JukeCard {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("No matches yet")
                            .font(.headline)
                            .foregroundColor(JukePalette.text)
                        Text("Double-check your spelling or try widening the filters.")
                            .foregroundColor(JukePalette.muted)
                    }
                }
            }

            if shouldShow(.profiles) && !viewModel.profileResults.isEmpty {
                resultSection(title: "People", icon: "person.2.fill") {
                    ForEach(viewModel.profileResults) { profile in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(profile.displayName.isEmpty ? profile.username : profile.displayName)
                                .font(.headline)
                                .foregroundColor(JukePalette.text)
                            if !profile.tagline.isEmpty {
                                Text(profile.tagline)
                                    .font(.subheadline)
                                    .foregroundColor(JukePalette.muted)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 6)
                    }
                }
            }

            if shouldShow(.artists) && !viewModel.artists.isEmpty {
                resultSection(title: "Artists", icon: "sparkles") {
                    ForEach(viewModel.artists) { artist in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(artist.name)
                                .font(.headline)
                                .foregroundColor(JukePalette.text)
                            if let genres = artist.genres, !genres.isEmpty {
                                Text(genres.joined(separator: ", "))
                                    .font(.footnote)
                                    .foregroundColor(JukePalette.muted)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 6)
                    }
                }
            }

            if shouldShow(.albums) && !viewModel.albums.isEmpty {
                resultSection(title: "Albums", icon: "square.stack.fill") {
                    ForEach(viewModel.albums) { album in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(album.name)
                                .font(.headline)
                                .foregroundColor(JukePalette.text)
                            HStack {
                                if let primaryArtist = album.artists?.first {
                                    Text(primaryArtistName(primaryArtist))
                                }
                                Spacer()
                                Text(album.releaseDate)
                            }
                            .font(.footnote)
                            .foregroundColor(JukePalette.muted)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 6)
                    }
                }
            }

            if shouldShow(.tracks) && !viewModel.tracks.isEmpty {
                resultSection(title: "Tracks", icon: "music.note.list") {
                    ForEach(viewModel.tracks) { track in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(track.name)
                                .font(.headline)
                                .foregroundColor(JukePalette.text)
                            Text(trackSubtitle(track))
                                .font(.footnote)
                                .foregroundColor(JukePalette.muted)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 6)
                    }
                }
            }
        }
    }

    private func resultSection<Content: View>(title: String, icon: String, @ViewBuilder content: () -> Content) -> some View {
        JukeCard {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 8) {
                    Image(systemName: icon)
                        .foregroundColor(JukePalette.accent)
                    Text(title.uppercased())
                        .font(.caption)
                        .foregroundColor(JukePalette.muted)
                        .kerning(1.2)
                }
                content()
            }
        }
    }

    private enum SearchScope: String, CaseIterable, Identifiable {
        case profiles
        case artists
        case albums
        case tracks

        var id: Self { self }

        var title: String {
            switch self {
            case .profiles: return "People"
            case .artists: return "Artists"
            case .albums: return "Albums"
            case .tracks: return "Tracks"
            }
        }
    }

    private func toggle(_ scope: SearchScope) {
        if activeScopes.contains(scope) {
            activeScopes.remove(scope)
        } else {
            activeScopes.insert(scope)
        }
    }

    private func shouldShow(_ scope: SearchScope) -> Bool {
        activeScopes.contains(scope)
    }

    private var shouldShowEmptyState: Bool {
        let hasQuery = !viewModel.query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        let noResults = viewModel.profileResults.isEmpty && viewModel.artists.isEmpty && viewModel.albums.isEmpty && viewModel.tracks.isEmpty
        return hasQuery && noResults && !viewModel.isLoading && viewModel.errorMessage == nil
    }

    private func primaryArtistName(_ reference: ArtistReference) -> String {
        switch reference {
        case .full(let artist):
            return artist.name
        case .identifier(let identifier):
            return "Artist #\(identifier)"
        case .name(let name):
            return name
        }
    }

    private func trackSubtitle(_ track: Track) -> String {
        let albumName: String
        if let album = track.album {
            switch album {
            case .full(let album):
                albumName = album.name
            case .identifier(let identifier):
                albumName = "Album #\(identifier)"
            case .name(let name):
                albumName = name
            case .none:
                albumName = "Single"
            }
        } else {
            albumName = "Single"
        }
        return "\(albumName) • \(formatDuration(track.duration))"
    }

    private func formatDuration(_ ms: Int) -> String {
        let seconds = ms / 1000
        let minutes = seconds / 60
        let remainingSeconds = seconds % 60
        return String(format: "%d:%02d", minutes, remainingSeconds)
    }
}

#Preview {
    let session = SessionStore()
    session.logout()
    return SearchDashboardView(session: session)
        .environmentObject(session)
}
