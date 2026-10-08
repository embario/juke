import SwiftUI

/// Pure helpers for Library browsing (artist -> albums, album -> tracks).
enum LibraryBrowsing {
    /// The catalog row for a crate item: matched on Spotify id, else the first row with the same name.
    static func match(_ results: [CatalogSearchResult], spotifyID: String, title: String) -> CatalogSearchResult? {
        results.first { $0.spotifyID == spotifyID }
            ?? results.first { $0.name.caseInsensitiveCompare(title) == .orderedSame }
    }

    static func trackSeed(_ track: CatalogTrackDetail, in album: CatalogAlbumDetail, artist: String?) -> Radio.Seed? {
        guard let id = track.spotifyID, !id.isEmpty else { return nil }
        return Radio.Seed(kind: .track, spotifyId: id, title: track.name, subtitle: artist ?? album.name, artworkUrl: album.spotifyData?.images?.first)
    }

    static func albumSeed(_ album: CatalogAlbumSummary, artist: String?) -> Radio.Seed? {
        guard let id = album.spotifyID, !id.isEmpty else { return nil }
        return Radio.Seed(kind: .album, spotifyId: id, title: album.name, subtitle: artist, artworkUrl: album.spotifyData?.images?.first)
    }

    static func albumSeed(_ album: CatalogAlbumDetail, artist: String?) -> Radio.Seed? {
        guard let id = album.spotifyID, !id.isEmpty else { return nil }
        return Radio.Seed(kind: .album, spotifyId: id, title: album.name, subtitle: artist, artworkUrl: album.spotifyData?.images?.first)
    }

    static func duration(_ ms: Int?) -> String? {
        ms.map { MemorySong.timestamp(Double($0) / 1000) }
    }
}

/// Shared actions: play something now, or start a station from a seed.
@MainActor
private struct LibraryActions {
    let model: VibeAppModel

    func play(spotifyID: String, kind: String) async -> String? {
        guard let token = model.session?.accessToken else { return "Sign in to play." }
        do { _ = try await PlaybackClient().play(token: token, spotifyID: spotifyID, kind: kind, deviceID: nil); return nil }
        catch { return (error as? LocalizedError)?.errorDescription ?? "Spotify couldn’t play that." }
    }

    func station(from seed: Radio.Seed) {
        model.coordinator.openNewStation(.init(start: .records, seeds: [seed], feelings: []))
        model.tab = .radio
    }
}

/// Loads a catalog detail for a crate item, resolving its catalog id through search.
private enum CatalogLoad<Value: Sendable>: Sendable {
    case loading, loaded(Value), failed(String)
}

struct AlbumBrowser: View {
    @Environment(VibeAppModel.self) private var model
    let title: String
    let spotifyID: String
    var artist: String?
    var catalogID: Int?
    @State private var state: CatalogLoad<CatalogAlbumDetail> = .loading
    @State private var message: String?

    var body: some View {
        List {
            switch state {
            case .loading: ProgressView().frame(maxWidth: .infinity).listRowBackground(Color.clear)
            case .failed(let text): Text(text).foregroundStyle(.secondary)
            case .loaded(let album):
                Section {
                    HStack(spacing: 12) {
                        AsyncImage(url: album.artworkURL) { $0.resizable().scaledToFill() } placeholder: { Color.secondary.opacity(0.15) }
                            .frame(width: 72, height: 72).clipShape(RoundedRectangle(cornerRadius: 10))
                        VStack(alignment: .leading) {
                            Text(album.name).font(.headline)
                            if let artist { Text(artist).font(.subheadline).foregroundStyle(.secondary) }
                        }
                    }
                    Button("Play from the beginning", systemImage: "play.fill") { play(album.spotifyID ?? spotifyID, "albums") }
                    if let seed = LibraryBrowsing.albumSeed(album, artist: artist) {
                        Button("Start a station from this album", systemImage: "dot.radiowaves.left.and.right") { LibraryActions(model: model).station(from: seed) }
                    }
                }
                Section("Tracks") {
                    ForEach(album.tracks) { track in
                        Button { if let id = track.spotifyID { play(id, "tracks") } } label: {
                            HStack {
                                Text("\(track.trackNumber ?? 0)").font(.caption).foregroundStyle(.secondary).frame(width: 24)
                                Text(track.name).lineLimit(1)
                                Spacer()
                                if let length = LibraryBrowsing.duration(track.durationMs) { Text(length).font(.caption).foregroundStyle(.secondary) }
                            }
                        }
                        .foregroundStyle(.primary)
                        .contextMenu {
                            if let seed = LibraryBrowsing.trackSeed(track, in: album, artist: artist) {
                                Button("Start a station from this song", systemImage: "dot.radiowaves.left.and.right") { LibraryActions(model: model).station(from: seed) }
                            }
                        }
                        .swipeActions {
                            if let seed = LibraryBrowsing.trackSeed(track, in: album, artist: artist) {
                                Button("Station") { LibraryActions(model: model).station(from: seed) }.tint(.accentColor)
                            }
                        }
                        .accessibilityHint("Plays now. Long press to start a station from this song.")
                    }
                }
            }
            if let message { Text(message).font(.footnote).foregroundStyle(.secondary) }
        }
        .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func play(_ id: String, _ kind: String) {
        Task { message = await LibraryActions(model: model).play(spotifyID: id, kind: kind) }
    }

    private func load() async {
        guard let token = model.session?.accessToken else { state = .failed("Sign in to browse."); return }
        let client = CatalogClient()
        do {
            let pk: Int
            if let catalogID { pk = catalogID }
            else if let found = LibraryBrowsing.match(try await client.search(title, kind: "albums", token: token), spotifyID: spotifyID, title: title) { pk = found.pk }
            else { state = .failed("This album isn’t in the catalog yet."); return }
            state = .loaded(try await client.album(id: pk, token: token))
        } catch { state = .failed((error as? LocalizedError)?.errorDescription ?? "The album couldn’t be loaded.") }
    }
}

struct ArtistBrowser: View {
    @Environment(VibeAppModel.self) private var model
    let title: String
    let spotifyID: String
    @State private var state: CatalogLoad<CatalogArtistDetail> = .loading
    @State private var message: String?

    var body: some View {
        List {
            switch state {
            case .loading: ProgressView().frame(maxWidth: .infinity).listRowBackground(Color.clear)
            case .failed(let text): Text(text).foregroundStyle(.secondary)
            case .loaded(let artist):
                if artist.albums.isEmpty { Text("No albums found.").foregroundStyle(.secondary) }
                ForEach(artist.albums) { album in
                    HStack(spacing: 12) {
                        AsyncImage(url: album.artworkURL) { $0.resizable().scaledToFill() } placeholder: { Color.secondary.opacity(0.15) }
                            .frame(width: 56, height: 56).clipShape(RoundedRectangle(cornerRadius: 8))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(album.name).lineLimit(1)
                            if let year = album.releaseDate?.prefix(4) { Text(year).font(.caption).foregroundStyle(.secondary) }
                        }
                        Spacer()
                        Menu {
                            if let id = album.spotifyID { Button("Play from the beginning", systemImage: "play.fill") { play(id) } }
                            NavigationLink("View album", value: album.pk)
                            if let seed = LibraryBrowsing.albumSeed(album, artist: artist.name) {
                                Button("Start a station from this album", systemImage: "dot.radiowaves.left.and.right") { LibraryActions(model: model).station(from: seed) }
                            }
                        } label: { Image(systemName: "ellipsis.circle").imageScale(.large) }
                            .accessibilityLabel("Actions for \(album.name)")
                    }
                    .background(NavigationLink("", value: album.pk).opacity(0))
                }
            }
            if let message { Text(message).font(.footnote).foregroundStyle(.secondary) }
        }
        .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
        .navigationDestination(for: Int.self) { pk in
            AlbumBrowser(title: albumName(pk), spotifyID: "", artist: title, catalogID: pk)
        }
        .task { await load() }
    }

    private func albumName(_ pk: Int) -> String {
        if case .loaded(let artist) = state { return artist.albums.first { $0.pk == pk }?.name ?? "Album" }
        return "Album"
    }

    private func play(_ albumID: String) { Task { message = await LibraryActions(model: model).play(spotifyID: albumID, kind: "albums") } }

    private func load() async {
        guard let token = model.session?.accessToken else { state = .failed("Sign in to browse."); return }
        let client = CatalogClient()
        do {
            guard let found = LibraryBrowsing.match(try await client.search(title, kind: "artists", token: token), spotifyID: spotifyID, title: title) else {
                state = .failed("This artist isn’t in the catalog yet."); return
            }
            state = .loaded(try await client.artist(id: found.pk, token: token))
        } catch { state = .failed((error as? LocalizedError)?.errorDescription ?? "The artist couldn’t be loaded.") }
    }
}
