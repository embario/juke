import SwiftUI

private enum CatalogRoute: Hashable {
    case album(Int, highlightedSpotifyID: String?)
    case artist(Int)
}

struct DiscoverView: View {
    @Environment(\.jukeTheme) private var theme
    @Environment(AppModel.self) private var model
    @State private var query = ""
    @State private var kind = "tracks"
    @State private var results: [CatalogSearchResult] = []
    @State private var path: [CatalogRoute] = []
    @State private var isSearching = false
    @State private var isResolvingResult = false
    private let catalog = CatalogClient()

    var body: some View {
        NavigationStack(path: $path) {
            searchCanvas
                .navigationDestination(for: CatalogRoute.self) { route in
                    switch route {
                    case .album(let id, let highlightedSpotifyID):
                        AlbumDetailPage(albumID: id, highlightedSpotifyID: highlightedSpotifyID)
                    case .artist(let id):
                        ArtistDetailPage(artistID: id)
                    }
                }
        }
    }

    private var searchCanvas: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Follow a sound").font(.system(size: 32, weight: .semibold, design: .rounded))
                if model.detection.canStartSpotifyPlayback {
                    Text("Search Spotify's full catalog through Juke. Select anything to explore its music and connections.")
                        .foregroundStyle(.secondary)
                } else {
                    Label("Spectator mode · Spotify's full catalog remains open for browsing", systemImage: "eye")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.secondary)
                        .accessibilityElement(children: .combine)
                        .accessibilityIdentifier("discover.spectatorMode")
                }
            }
            HStack {
                TextField("Search songs, artists, or albums", text: $query)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("discover.query")
                    .onSubmit { search() }
                Picker("Type", selection: $kind) {
                    Text("Songs").tag("tracks")
                    Text("Artists").tag("artists")
                    Text("Albums").tag("albums")
                }
                .frame(width: 120)
                Button("Search") { search() }
                    .buttonStyle(.borderedProminent)
                    .tint(theme.accent.color)
                    .disabled(query.trimmingCharacters(in: .whitespaces).isEmpty || isSearching)
                    .accessibilityIdentifier("discover.search")
            }
            if isSearching || isResolvingResult { ProgressView() }
            ScrollView {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 16)], spacing: 16) {
                    ForEach(results) { result in
                        CatalogResultCard(result: result, kind: kind) { open(result) }
                    }
                }
                .padding(2)
            }
            .scrollIndicators(.hidden)
        }
        .padding(30)
        .navigationTitle("Discover")
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

    private func open(_ result: CatalogSearchResult) {
        if kind == "artists" {
            path.append(.artist(result.pk))
            return
        }
        if kind == "albums" {
            path.append(.album(result.pk, highlightedSpotifyID: nil))
            return
        }
        if let albumPK = result.albumPK {
            path.append(.album(albumPK, highlightedSpotifyID: result.spotifyID))
            return
        }
        guard let token = model.session?.accessToken else { return }
        isResolvingResult = true
        Task {
            do {
                let album = try await catalog.album(for: result, token: token)
                path.append(.album(album.pk, highlightedSpotifyID: result.spotifyID))
            } catch {
                model.banner = error.localizedDescription
            }
            isResolvingResult = false
        }
    }
}

private struct CatalogResultCard: View {
    @Environment(\.jukeTheme) private var theme
    @Environment(AppModel.self) private var model
    let result: CatalogSearchResult
    let kind: String
    let open: () -> Void
    @State private var artworkURL: URL?
    @State private var isHovered = false
    private let catalog = CatalogClient()

    var body: some View {
        Button(action: open) {
            VStack(alignment: .leading, spacing: 9) {
                AsyncImage(url: artworkURL ?? result.resolvedArtworkURL) { image in
                    image.resizable().scaledToFill()
                } placeholder: {
                    Rectangle()
                        .fill(theme.accent.color.opacity(0.15))
                        .overlay(Image(systemName: "music.note").font(.title2).foregroundStyle(theme.accent.color))
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
                HStack(spacing: 5) {
                    Image(systemName: "dot.radiowaves.left.and.right")
                    Text("SPOTIFY")
                }
                .font(.caption2.weight(.bold))
                .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18))
            .overlay {
                RoundedRectangle(cornerRadius: 18)
                    .strokeBorder(theme.accent.color.opacity(isHovered ? 0.7 : 0.12), lineWidth: isHovered ? 2 : 1)
            }
            .scaleEffect(isHovered ? 1.018 : 1)
            .shadow(color: theme.accent.color.opacity(isHovered ? 0.2 : 0), radius: 12, y: 4)
        }
        .buttonStyle(.plain)
        .contentShape(RoundedRectangle(cornerRadius: 18))
        .onHover { hovering in
            withAnimation(.easeOut(duration: 0.14)) { isHovered = hovering }
        }
        .task(id: result.pk) {
            guard artworkURL == nil, let token = model.session?.accessToken else { return }
            artworkURL = await catalog.artwork(for: result, kind: kind, token: token)
        }
        .help("Open details")
        .accessibilityHint("Open details")
        .accessibilityIdentifier("discover.result.\(result.pk)")
    }
}

private struct AlbumDetailPage: View {
    @Environment(AppModel.self) private var model
    let albumID: Int
    let highlightedSpotifyID: String?
    @State private var album: CatalogAlbumDetail?
    @State private var failure: String?
    private let catalog = CatalogClient()

    var body: some View {
        Group {
            if let album { albumCanvas(album) }
            else if let failure { ContentUnavailableView("Album unavailable", systemImage: "exclamationmark.triangle", description: Text(failure)) }
            else { ProgressView("Opening album…") }
        }
        .navigationTitle(album?.name ?? "Album")
        .task(id: albumID) {
            guard let token = model.session?.accessToken else { return }
            do { album = try await catalog.album(id: albumID, token: token) }
            catch { failure = error.localizedDescription }
        }
    }

    private func albumCanvas(_ album: CatalogAlbumDetail) -> some View {
        ZStack {
            CatalogArtworkBackdrop(url: album.artworkURL)
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    if !model.detection.canStartSpotifyPlayback { SpectatorPlaybackHint() }
                    HStack(alignment: .bottom, spacing: 24) {
                        CatalogArtwork(url: album.artworkURL, symbol: "square.stack.fill", size: 210)
                        VStack(alignment: .leading, spacing: 9) {
                            Text((album.albumType ?? "ALBUM").uppercased())
                                .font(.caption.weight(.bold)).tracking(1.5).foregroundStyle(.secondary)
                            Text(album.name).font(.system(size: 38, weight: .bold, design: .rounded))
                            Text(albumMetadata(album)).foregroundStyle(.secondary)
                            if let spotifyURL = album.spotifyURL {
                                Link("Open in Spotify", destination: spotifyURL)
                                    .font(.subheadline.weight(.semibold))
                            }
                        }
                    }
                    if let description = album.description, !description.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            detailHeading("About this album")
                            Text(description).font(.title3).lineSpacing(4).textSelection(.enabled)
                        }
                    }
                    VStack(alignment: .leading, spacing: 10) {
                        detailHeading("Tracks")
                        ForEach(album.tracks) { track in
                            AlbumTrackRow(
                                track: track,
                                album: album,
                                isHighlighted: track.spotifyID == highlightedSpotifyID
                            )
                        }
                    }
                    if !album.relatedAlbums.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            detailHeading("Keep exploring")
                            ScrollView(.horizontal) {
                                HStack(spacing: 14) {
                                    ForEach(album.relatedAlbums) { related in
                                        NavigationLink(value: CatalogRoute.album(related.pk, highlightedSpotifyID: nil)) {
                                            CatalogResourceTile(name: related.name, artworkURL: related.artworkURL, caption: related.releaseDate)
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }
                            .scrollIndicators(.hidden)
                        }
                    }
                }
                .padding(32)
                .frame(maxWidth: 920, alignment: .leading)
            }
            .scrollIndicators(.hidden)
        }
        .accessibilityIdentifier("catalog.albumDetail")
    }

    private func albumMetadata(_ album: CatalogAlbumDetail) -> String {
        [album.releaseDate, album.totalTracks.map { "\($0) tracks" }].compactMap { $0 }.joined(separator: " · ")
    }
}

private struct AlbumTrackRow: View {
    @Environment(\.jukeTheme) private var theme
    @Environment(AppModel.self) private var model
    let track: CatalogTrackDetail
    let album: CatalogAlbumDetail
    let isHighlighted: Bool
    @State private var isHovered = false

    var body: some View {
        HStack(spacing: 13) {
            Text("\(track.trackNumber ?? 0)")
                .monospacedDigit().foregroundStyle(.secondary).frame(width: 24, alignment: .trailing)
            Text(track.name).font(.body.weight(isHighlighted ? .semibold : .regular))
            Spacer()
            Text(formatDuration(track.durationMs)).monospacedDigit().foregroundStyle(.secondary)
            if model.detection.canStartSpotifyPlayback, track.spotifyID != nil {
                Button {
                    Task { await model.play(track, albumName: album.name) }
                } label: {
                    Image(systemName: "play.fill").frame(width: 26, height: 26)
                }
                .buttonStyle(.borderless)
                .help("Play in Spotify")
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(
            theme.accent.color.opacity(isHighlighted ? 0.24 : (isHovered ? 0.12 : 0)),
            in: RoundedRectangle(cornerRadius: 11)
        )
        .onHover { hovering in withAnimation(.easeOut(duration: 0.12)) { isHovered = hovering } }
        .accessibilityIdentifier(isHighlighted ? "catalog.track.highlighted" : "catalog.track.\(track.pk)")
    }
}

private struct ArtistDetailPage: View {
    @Environment(AppModel.self) private var model
    let artistID: Int
    @State private var artist: CatalogArtistDetail?
    @State private var failure: String?
    private let catalog = CatalogClient()

    var body: some View {
        Group {
            if let artist { artistCanvas(artist) }
            else if let failure { ContentUnavailableView("Artist unavailable", systemImage: "exclamationmark.triangle", description: Text(failure)) }
            else { ProgressView("Opening artist…") }
        }
        .navigationTitle(artist?.name ?? "Artist")
        .task(id: artistID) {
            guard let token = model.session?.accessToken else { return }
            do { artist = try await catalog.artist(id: artistID, token: token) }
            catch { failure = error.localizedDescription }
        }
    }

    private func artistCanvas(_ artist: CatalogArtistDetail) -> some View {
        ZStack {
            CatalogArtworkBackdrop(url: artist.artworkURL)
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    if !model.detection.canStartSpotifyPlayback { SpectatorPlaybackHint() }
                    HStack(alignment: .bottom, spacing: 24) {
                        CatalogArtwork(url: artist.artworkURL, symbol: "person.wave.2.fill", size: 210)
                        VStack(alignment: .leading, spacing: 10) {
                            Text("ARTIST").font(.caption.weight(.bold)).tracking(1.5).foregroundStyle(.secondary)
                            Text(artist.name).font(.system(size: 40, weight: .bold, design: .rounded))
                            Text(artist.genres.map(\.name).joined(separator: " · ")).foregroundStyle(.secondary)
                            if let spotifyURL = artist.spotifyURL {
                                Link("Open in Spotify", destination: spotifyURL)
                                    .font(.subheadline.weight(.semibold))
                            }
                        }
                    }
                    if let bio = artist.bio, !bio.isEmpty {
                        Text(bio).font(.title3).lineSpacing(4).textSelection(.enabled)
                    }
                    if !artist.topTracks.isEmpty {
                        VStack(alignment: .leading, spacing: 10) {
                            detailHeading("Top songs")
                            ForEach(artist.topTracks) { track in
                                HStack {
                                    Text(track.name).font(.body.weight(.medium))
                                    Spacer()
                                    Text(formatDuration(track.durationMs)).monospacedDigit().foregroundStyle(.secondary)
                                    if model.detection.canStartSpotifyPlayback, track.spotifyID != nil {
                                        Button { Task { await model.play(track, albumName: "Juke catalog", artistName: artist.name) } } label: {
                                            Image(systemName: "play.fill").frame(width: 26, height: 26)
                                        }
                                        .buttonStyle(.borderless)
                                    }
                                }
                                .padding(.vertical, 8)
                            }
                        }
                    }
                    if !artist.albums.isEmpty {
                        resourceShelf("Albums", albums: artist.albums)
                    }
                    if !artist.relatedArtists.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            detailHeading("Related artists")
                            ScrollView(.horizontal) {
                                HStack(spacing: 14) {
                                    ForEach(artist.relatedArtists) { related in
                                        NavigationLink(value: CatalogRoute.artist(related.pk)) {
                                            CatalogResourceTile(name: related.name, artworkURL: related.artworkURL, caption: "Artist")
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }
                            .scrollIndicators(.hidden)
                        }
                    }
                }
                .padding(32)
                .frame(maxWidth: 920, alignment: .leading)
            }
            .scrollIndicators(.hidden)
        }
        .accessibilityIdentifier("catalog.artistDetail")
    }

    private func resourceShelf(_ title: String, albums: [CatalogAlbumSummary]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            detailHeading(title)
            ScrollView(.horizontal) {
                HStack(spacing: 14) {
                    ForEach(albums) { album in
                        NavigationLink(value: CatalogRoute.album(album.pk, highlightedSpotifyID: nil)) {
                            CatalogResourceTile(name: album.name, artworkURL: album.artworkURL, caption: album.releaseDate)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .scrollIndicators(.hidden)
        }
    }
}

private struct SpectatorPlaybackHint: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "eye")
            Text("You're browsing in spectator mode. Connect Spotify only if you'd like Juke to control playback.")
            Spacer()
            Button("Connect Spotify") { model.openSpotifyConnection() }
                .buttonStyle(.bordered)
        }
        .font(.subheadline)
        .padding(12)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
        .accessibilityIdentifier("catalog.spectatorHint")
    }
}

private struct CatalogResourceTile: View {
    let name: String
    let artworkURL: URL?
    let caption: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            CatalogArtwork(url: artworkURL, symbol: "music.note", size: 132)
            Text(name).font(.headline).lineLimit(2)
            if let caption { Text(caption).font(.caption).foregroundStyle(.secondary).lineLimit(1) }
        }
        .frame(width: 132, alignment: .leading)
    }
}

private struct CatalogArtwork: View {
    let url: URL?
    let symbol: String
    let size: CGFloat

    var body: some View {
        AsyncImage(url: url) { image in image.resizable().scaledToFill() } placeholder: {
            Rectangle().fill(.white.opacity(0.08)).overlay(Image(systemName: symbol).font(.title).foregroundStyle(.secondary))
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: size * 0.08))
        .shadow(color: .black.opacity(0.25), radius: 18, y: 8)
    }
}

private struct CatalogArtworkBackdrop: View {
    let url: URL?

    var body: some View {
        AsyncImage(url: url) { image in
            image.resizable().scaledToFill().blur(radius: 55).opacity(0.28)
        } placeholder: {
            Color.clear
        }
        .ignoresSafeArea()
        .overlay(.ultraThinMaterial.opacity(0.55))
        .allowsHitTesting(false)
    }
}

private func detailHeading(_ title: String) -> some View {
    Text(title.uppercased()).font(.caption.weight(.bold)).tracking(1.5).foregroundStyle(.secondary)
}

private func formatDuration(_ milliseconds: Int?) -> String {
    guard let milliseconds else { return "—" }
    let seconds = max(0, milliseconds / 1_000)
    return "\(seconds / 60):\(String(format: "%02d", seconds % 60))"
}
