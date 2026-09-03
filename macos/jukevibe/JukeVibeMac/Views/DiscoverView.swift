import SwiftUI

struct DiscoverView: View {
    @Environment(AppModel.self) private var model
    @State private var query = ""
    @State private var kind = "tracks"
    @State private var results: [CatalogSearchResult] = []
    @State private var isSearching = false
    private let catalog = CatalogClient()

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Follow a sound").font(.system(size: 32, weight: .semibold, design: .rounded))
                Text("Browse Juke's connected music catalog. Double-click any result to begin listening in Spotify.").foregroundStyle(.secondary)
            }
            HStack {
                TextField("Search songs, artists, or albums", text: $query)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("discover.query")
                    .onSubmit { search() }
                Picker("Type", selection: $kind) { Text("Songs").tag("tracks"); Text("Artists").tag("artists"); Text("Albums").tag("albums") }.frame(width: 120)
                Button("Search") { search() }
                    .buttonStyle(.borderedProminent)
                    .tint(model.atmosphere.primary)
                    .disabled(query.trimmingCharacters(in: .whitespaces).isEmpty || isSearching)
                    .accessibilityIdentifier("discover.search")
            }
            if isSearching { ProgressView() }
            ScrollView {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 16)], spacing: 16) {
                    ForEach(results) { result in
                        CatalogResultCard(result: result, kind: kind)
                    }
                }
            }
        }.padding(30).navigationTitle("Discover")
    }

    private func search() {
        guard let token = model.session?.accessToken else { return }
        isSearching = true
        Task {
            do { results = try await catalog.search(query, kind: kind, token: token) }
            catch { model.banner = error.localizedDescription }
            isSearching = false
        }
    }
}

private struct CatalogResultCard: View {
    @Environment(AppModel.self) private var model
    let result: CatalogSearchResult
    let kind: String
    @State private var artworkURL: URL?
    private let catalog = CatalogClient()

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            AsyncImage(url: artworkURL ?? result.resolvedArtworkURL) { image in
                image.resizable().scaledToFill()
            } placeholder: {
                Rectangle()
                    .fill(model.atmosphere.primary.opacity(0.15))
                    .overlay(Image(systemName: "music.note").font(.title2).foregroundStyle(model.atmosphere.primary))
            }
            .aspectRatio(1, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 14))

            Text(result.name)
                .font(.headline.weight(.bold))
                .lineLimit(2)
            if let artist = result.artistNames, !artist.isEmpty {
                Label(artist, systemImage: "person.fill")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            if let album = result.albumName, !album.isEmpty {
                Label(album, systemImage: "square.stack.fill")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .padding(12)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18))
        .contentShape(RoundedRectangle(cornerRadius: 18))
        .onTapGesture(count: 2) { Task { await model.play(result, kind: kind) } }
        .task(id: result.pk) {
            guard artworkURL == nil, let token = model.session?.accessToken else { return }
            artworkURL = await catalog.artwork(for: result, token: token)
        }
        .help(result.spotifyID == nil ? "This result is not playable yet" : "Double-click to play in Spotify")
        .accessibilityHint(result.spotifyID == nil ? "No Spotify playback reference" : "Double-click to play")
        .accessibilityAction(named: "Play in Spotify") { Task { await model.play(result, kind: kind) } }
        .accessibilityIdentifier("discover.result.\(result.pk)")
    }
}

struct PrivateListeningLibraryView: View {
    @Environment(AppModel.self) private var model
    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            Text("Your Juke library").font(.system(size: 32, weight: .semibold, design: .rounded))
            Text("Saved music and provider connections will live here. The first build keeps this surface intentionally small while catalog browsing and listening context connect to Neptune.")
                .foregroundStyle(.secondary).frame(maxWidth: 560, alignment: .leading)
            HStack(spacing: 16) {
                libraryCard("Spotify", symbol: "dot.radiowaves.left.and.right", detail: "Connect and browse through Juke")
                libraryCard("Apple Music", symbol: "music.note", detail: "Current playback is detected locally")
            }
            Spacer()
        }.padding(30).frame(maxWidth: .infinity, alignment: .leading).navigationTitle("Library")
    }

    private func libraryCard(_ title: String, symbol: String, detail: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: symbol).font(.title).foregroundStyle(model.atmosphere.primary)
            Text(title).font(.headline)
            Text(detail).font(.caption).foregroundStyle(.secondary)
        }.frame(maxWidth: 220, alignment: .leading).padding(18).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18))
    }
}
