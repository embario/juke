import SwiftUI

/// An artist: the picture, name and genres over the full release catalog, with the bio, top songs
/// and related artists brought down by a downward swipe (or the button). Reachable from Library and Radio.
struct ArtistDetailView: View {
    @Environment(VibeAppModel.self) private var model
    let title: String
    let spotifyID: String
    /// Set when opened from "Related artists", which know the catalog id but not the Spotify id.
    var catalogID: Int?
    @State private var resolution: CatalogLoad<ArtistCatalogModel> = .loading
    @State private var details: CatalogLoad<CatalogArtistDetail> = .loading
    @State private var message: String?
    @State private var showsDetails = false

    var body: some View {
        DetailReveal(revealed: $showsDetails, showLabel: "Show details", hideLabel: "Back to releases", idPrefix: "artist") {
            hero
        } content: {
            releases
        } details: {
            detailsPane
        }
        .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
        .background(VibeBackground(atmosphere: model.atmosphere))
        .navigationDestination(for: Int.self) { pk in
            AlbumDetailView(title: albumName(pk), spotifyID: "", artist: title, catalogID: pk)
        }
        .navigationDestination(for: RelatedArtistRoute.self) { route in
            ArtistDetailView(title: route.name, spotifyID: "", catalogID: route.pk)
        }
        .task { await load() }
        #if DEBUG
        .onChange(of: detailsLoaded) { _, loaded in
            // `--uitesting-artist-details` opens with the details down (for screenshots).
            if loaded, ProcessInfo.processInfo.arguments.contains("--uitesting-artist-details") { showsDetails = true }
        }
        #endif
    }

    private var detailsLoaded: Bool { if case .loaded = details { true } else { false } }
    private var loadedDetails: CatalogArtistDetail? { if case .loaded(let artist) = details { artist } else { nil } }

    private func albumName(_ pk: Int) -> String {
        if case .loaded(let catalog) = resolution { return catalog.release(pk: pk)?.name ?? "Album" }
        return "Album"
    }

    // MARK: Panes

    private var hero: some View {
        VStack(spacing: 8) {
            AsyncImage(url: loadedDetails?.artworkURL) { $0.resizable().scaledToFill() } placeholder: {
                ZStack { Color.secondary.opacity(0.15); Image(systemName: "person.fill").font(.system(size: 40)).foregroundStyle(.secondary) }
            }
            .frame(width: 120, height: 120).clipShape(Circle()).shadow(color: .black.opacity(0.25), radius: 10, y: 6)
            Text(title).font(.title3.bold()).multilineTextAlignment(.center).lineLimit(2)
            if let genres = LibraryBrowsing.genreLine(loadedDetails) { Text(genres).font(.caption).foregroundStyle(.secondary).lineLimit(1) }
        }
        .padding(.top, 12).padding(.horizontal, 20).frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
    }

    private var releases: some View {
        VStack(spacing: 0) {
            if case .loaded(let catalog) = resolution { ArtistKindFilter(catalog: catalog) }
            List {
                switch resolution {
                case .loading: ProgressView().frame(maxWidth: .infinity).listRowBackground(Color.clear)
                case .failed(let text):
                    Text(text).foregroundStyle(.secondary)
                    Button("Try again") { Task { await retry() } }
                case .loaded(let catalog): ArtistCatalogList(catalog: catalog, artist: title, message: $message)
                }
                if let message { Text(message).font(.footnote).foregroundStyle(.secondary) }
            }
            .scrollContentBackground(.hidden)
        }
    }

    @ViewBuilder private var detailsPane: some View {
        switch details {
        case .loading: ProgressView().frame(maxWidth: .infinity).padding(.top, 24)
        case .failed(let text):
            VStack(alignment: .leading, spacing: 8) {
                Text(text).foregroundStyle(.secondary)
                Button("Try again") { Task { await retry() } }
            }
        case .loaded(let artist):
            VStack(alignment: .leading, spacing: 14) {
                if let bio = artist.bio, !bio.isEmpty { Text(bio).font(.subheadline) }
                if !artist.genres.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack { ForEach(artist.genres) { Text($0.name).font(.caption.weight(.medium)).padding(.horizontal, 10).padding(.vertical, 5).background(Color.secondary.opacity(0.15), in: Capsule()) } }
                    }
                }
                if !artist.topTracks.isEmpty {
                    Text("Top songs").font(.headline)
                    ForEach(artist.topTracks) { track in
                        Button { if let id = track.spotifyID { Task { message = await LibraryActions(model: model).play(spotifyID: id, kind: "tracks") } } } label: {
                            HStack { Text(track.name).lineLimit(1); Spacer(); Image(systemName: "play.fill").font(.caption).foregroundStyle(.secondary) }
                                .frame(minHeight: 40).contentShape(Rectangle())
                        }.buttonStyle(.plain)
                    }
                }
                if !artist.relatedArtists.isEmpty {
                    Text("Related artists").font(.headline)
                    ForEach(artist.relatedArtists) { related in
                        NavigationLink(value: RelatedArtistRoute(pk: related.pk, name: related.name)) {
                            HStack { Text(related.name); Spacer(); Image(systemName: "chevron.right").font(.caption).foregroundStyle(.secondary) }
                                .frame(minHeight: 40).contentShape(Rectangle())
                        }.buttonStyle(.plain)
                    }
                }
                if artist.bio?.isEmpty != false, artist.topTracks.isEmpty, artist.relatedArtists.isEmpty, artist.genres.isEmpty {
                    Text("No more details for this artist yet.").foregroundStyle(.secondary)
                }
            }
        }
    }

    // MARK: Loading

    private func retry() async { resolution = .loading; details = .loading; await load() }

    private func load() async {
        guard case .loading = resolution else { return }
        guard let token = model.session?.accessToken else {
            resolution = .failed("Sign in to browse."); details = .failed("Sign in to browse."); return
        }
        let client = CatalogClient()
        do {
            let pk: Int
            if let catalogID { pk = catalogID }
            else if let found = LibraryBrowsing.match(try await client.search(title, kind: "artists", token: token), spotifyID: spotifyID) { pk = found.pk }
            else {
                resolution = .failed("This artist isn’t in the catalog yet."); details = .failed("This artist isn’t in the catalog yet."); return
            }
            let catalog = ArtistCatalogModel { kind, offset in
                try await client.releases(artistID: pk, kind: kind, offset: offset, token: token)
            }
            resolution = .loaded(catalog)
            // The bio and top songs load beside the catalog; one failing does not hide the other.
            Task {
                do { details = .loaded(try await client.artist(id: pk, token: token)) }
                catch is CancellationError { return }
                catch { details = .failed((error as? LocalizedError)?.errorDescription ?? "The artist’s details couldn’t be loaded.") }
            }
            await catalog.start()
        } catch is CancellationError { return }
        catch {
            let text = (error as? LocalizedError)?.errorDescription ?? "The artist couldn’t be loaded."
            resolution = .failed(text); details = .failed(text)
        }
    }
}

/// Release-type filters, pinned above the list so they stay reachable while scrolling a long catalog.
struct ArtistKindFilter: View {
    let catalog: ArtistCatalogModel

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(catalog.visibleKinds) { kind in
                    Button { Task { await catalog.select(kind) } } label: {
                        Text(catalog.title(for: kind)).font(.subheadline.weight(.medium))
                            .padding(.horizontal, 12).padding(.vertical, 7)
                            .background(kind == catalog.kind ? Color.accentColor : Color.secondary.opacity(0.15), in: Capsule())
                            .foregroundStyle(kind == catalog.kind ? Color.white : Color.primary)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("artist.filter.\(kind.rawValue)")
                    .accessibilityAddTraits(kind == catalog.kind ? .isSelected : [])
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 8)
        }
    }
}

/// The paginated release rows for one artist.
private struct ArtistCatalogList: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.detailSheetClose) private var closeSheet
    let catalog: ArtistCatalogModel
    let artist: String
    @Binding var message: String?

    var body: some View {
        let section = catalog.current
        if section.items.isEmpty, section.hasLoaded, section.error == nil {
            Text("No \(catalog.kind.title.lowercased()) found.").foregroundStyle(.secondary)
        }
        ForEach(section.items) { album in
            row(album)
                .onAppear { Task { await catalog.loadMore(after: album) } }
        }
        if section.isLoading { ProgressView().frame(maxWidth: .infinity).listRowBackground(Color.clear).accessibilityIdentifier("artist.loading") }
        if let error = section.error {
            VStack(alignment: .leading, spacing: 6) {
                Text(error).foregroundStyle(.secondary)
                Button("Try again") { Task { await catalog.retry() } }
            }
        }
    }

    private func row(_ album: CatalogAlbumSummary) -> some View {
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
                if let seed = LibraryBrowsing.albumSeed(album, artist: artist) {
                    Button("Start a station from this album", systemImage: "dot.radiowaves.left.and.right") {
                        LibraryActions(model: model).station(from: seed)
                        closeSheet?()
                    }
                }
            } label: { Image(systemName: "ellipsis.circle").imageScale(.large) }
                .accessibilityLabel("Actions for \(album.name)")
        }
        .background(NavigationLink("", value: album.pk).opacity(0))
    }

    private func play(_ albumID: String) { Task { message = await LibraryActions(model: model).play(spotifyID: albumID, kind: "albums") } }
}
