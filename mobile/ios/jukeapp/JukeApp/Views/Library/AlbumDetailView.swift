import SwiftUI

/// An album: the cover, play and station buttons, and its tracklist, which a downward swipe
/// (or the button) brings down over the pane. Reachable from Library, an artist's catalog and Radio.
struct AlbumDetailView: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.detailSheetClose) private var closeSheet
    let title: String
    let spotifyID: String
    var artist: String?
    var catalogID: Int?
    @State private var state: CatalogLoad<CatalogAlbumDetail> = .loading
    @State private var message: String?
    @State private var showsTracks = false

    var body: some View {
        DetailReveal(revealed: $showsTracks, showLabel: "Show tracks", hideLabel: "Back to album", idPrefix: "album") {
            hero
        } content: {
            pane
        } details: {
            tracklist
        }
        .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
        .background(VibeBackground(atmosphere: model.atmosphere))
        .task { model.recents.record(kind: .album, spotifyID: spotifyID, title: title, subtitle: artist); await load() }
        #if DEBUG
        .onChange(of: stateIsLoaded) { _, loaded in
            // `--uitesting-album-tracks` opens with the tracklist down (for screenshots).
            if loaded, ProcessInfo.processInfo.arguments.contains("--uitesting-album-tracks") { showsTracks = true }
        }
        #endif
    }

    private var stateIsLoaded: Bool { if case .loaded = state { true } else { false } }

    private var loadedAlbum: CatalogAlbumDetail? { if case .loaded(let album) = state { album } else { nil } }

    private var hero: some View {
        VStack(spacing: 10) {
            AsyncImage(url: loadedAlbum?.artworkURL) { $0.resizable().scaledToFill() } placeholder: {
                ZStack { Color.secondary.opacity(0.15); Image(systemName: "square.stack").font(.system(size: 44)).foregroundStyle(.secondary) }
            }
            .frame(width: 200, height: 200).clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .shadow(color: .black.opacity(0.28), radius: 14, y: 8)
            VStack(spacing: 2) {
                Text(title).font(.title3.bold()).multilineTextAlignment(.center).lineLimit(2)
                if let artist { Text(artist).font(.subheadline).foregroundStyle(.secondary).lineLimit(1) }
                if let album = loadedAlbum, !LibraryBrowsing.albumFacts(album).isEmpty {
                    Text(LibraryBrowsing.albumFacts(album)).font(.caption).foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.top, 16).padding(.horizontal, 20).frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
    }

    private var pane: some View {
        ScrollView { paneContent }
    }

    private var paneContent: some View {
        VStack(spacing: 12) {
            switch state {
            case .loading: ProgressView().padding(.top, 12)
            case .failed(let text):
                Text(text).foregroundStyle(.secondary).multilineTextAlignment(.center)
                Button("Try again") { Task { await retry() } }
            case .loaded(let album):
                Button { play(album.spotifyID ?? spotifyID, "albums") } label: { Label("Play from the beginning", systemImage: "play.fill").frame(maxWidth: .infinity) }
                    .buttonStyle(.borderedProminent).controlSize(.large)
                    .accessibilityIdentifier("album.play")
                if let seed = LibraryBrowsing.albumSeed(album, artist: artist) {
                    Button { startStation(seed) } label: { Label("Start a station from this album", systemImage: "dot.radiowaves.left.and.right").frame(maxWidth: .infinity) }
                        .buttonStyle(.bordered).controlSize(.large)
                }
            }
            if let message { Text(message).font(.footnote).foregroundStyle(.secondary) }
        }
        .padding(.horizontal, 20).padding(.top, 4).padding(.bottom, 16)
    }

    @ViewBuilder private var tracklist: some View {
        if let album = loadedAlbum {
            VStack(alignment: .leading, spacing: 10) {
                Text("Tracks").font(.headline)
                if let text = album.description, !text.isEmpty { Text(text).font(.subheadline).foregroundStyle(.secondary) }
                let discs = LibraryBrowsing.discs(album.tracks)
                if discs.isEmpty { Text("No tracklist yet.").foregroundStyle(.secondary) }
                ForEach(discs) { disc in
                    if discs.count > 1 { Text("Disc \(disc.number)").font(.footnote.weight(.semibold)).foregroundStyle(.secondary).padding(.top, 6) }
                    ForEach(disc.tracks, id: \.self) { index in row(album.tracks[index], in: album) }
                }
            }
        } else {
            Text("The tracklist appears once the album has loaded.").foregroundStyle(.secondary)
        }
    }

    private func row(_ track: CatalogTrackDetail, in album: CatalogAlbumDetail) -> some View {
        Button { if let id = track.spotifyID { play(id, "tracks") } } label: {
            HStack(spacing: 10) {
                Text(track.trackNumber.map(String.init) ?? "").font(.caption.monospacedDigit()).foregroundStyle(.secondary).frame(width: 24)
                Text(track.name).lineLimit(1)
                Spacer()
                if let length = LibraryBrowsing.duration(track.durationMs) { Text(length).font(.caption.monospacedDigit()).foregroundStyle(.secondary) }
            }
            .frame(minHeight: 40).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .contextMenu {
            if let seed = LibraryBrowsing.trackSeed(track, in: album, artist: artist) {
                Button("Start a station from this song", systemImage: "dot.radiowaves.left.and.right") { startStation(seed) }
            }
        }
        .accessibilityHint("Plays now. Long press to start a station from this song.")
    }

    private func startStation(_ seed: Radio.Seed) {
        LibraryActions(model: model).station(from: seed)
        closeSheet?()
    }

    private func play(_ id: String, _ kind: String) {
        Task { message = await LibraryActions(model: model).play(spotifyID: id, kind: kind) }
    }

    private func retry() async { state = .loading; await load() }

    private func load() async {
        guard case .loading = state else { return }
        guard let token = model.session?.accessToken else { state = .failed("Sign in to browse."); return }
        let client = CatalogClient()
        do {
            let pk: Int
            if let catalogID { pk = catalogID }
            else if let found = LibraryBrowsing.match(try await client.search(title, kind: "albums", token: token), spotifyID: spotifyID) { pk = found.pk }
            else { state = .failed("This album isn’t in the catalog yet."); return }
            state = .loaded(try await client.album(id: pk, token: token))
        } catch is CancellationError { return }
        catch { state = .failed((error as? LocalizedError)?.errorDescription ?? "The album couldn’t be loaded.") }
    }
}
