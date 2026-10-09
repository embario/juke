import SwiftUI

/// The crate on iPhone: the listener's personal crate, or Spotify search when a query is typed.
struct LibraryScreen: View {
    @Environment(VibeAppModel.self) private var model
    @State private var kind: Radio.SeedKind = .track
    @State private var query = ""
    /// The crate or the search results as the server sent them, and the query they answer.
    @State private var fetched: [Radio.CrateItem] = []
    @State private var fetchedQuery = ""
    @State private var loading = false
    @State private var error: String?
    @State private var selected: Radio.CrateItem?
    @State private var browsing: Radio.CrateItem?
    @State private var focus = 0
    @State private var loadTask: Task<Void, Never>?
    @AppStorage("juke.library.crateView") private var showsCrate = true
    @AppStorage("juke.settings.crateFlipDirection") private var flipRaw = CrateFlipDirection.sideToSide.rawValue

    private let columns = [GridItem(.adaptive(minimum: 150), spacing: 14)]
    /// Without a search: recent resources first, topped up from the crate while the history is short.
    private var items: [Radio.CrateItem] {
        fetchedQuery.isEmpty ? RecentLibrary.library(kind: kind, recents: model.recents.items, fill: fetched) : fetched
    }
    private var crateMode: CrateMode { CrateMode(CrateFlipDirection(rawValue: flipRaw) ?? .sideToSide) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Picker("Type", selection: $kind) {
                    Text("Songs").tag(Radio.SeedKind.track)
                    Text("Artists").tag(Radio.SeedKind.artist)
                    Text("Albums").tag(Radio.SeedKind.album)
                }.pickerStyle(.segmented)
                if let error { Text(error).font(.callout).foregroundStyle(.secondary) }
                if loading { ProgressView().frame(maxWidth: .infinity) }
                if showsCrate, !items.isEmpty {
                    CrateView(items: items, mode: crateMode, onSelect: { open($0) }, focus: $focus)
                        .padding(.top, CrateLayout.libraryTopClearance(for: crateMode))
                    if items.indices.contains(focus) {
                        VStack(spacing: 2) {
                            Text(items[focus].title).font(.headline).lineLimit(1)
                            if let subtitle = items[focus].subtitle { Text(subtitle).font(.subheadline).foregroundStyle(.secondary).lineLimit(1) }
                        }.frame(maxWidth: .infinity)
                    }
                } else {
                    LazyVGrid(columns: columns, spacing: 14) {
                        ForEach(items) { item in
                            Button { open(item) } label: { CrateCard(item: item) }.buttonStyle(.plain)
                        }
                    }
                }
                if !loading, items.isEmpty, error == nil {
                    Text(query.isEmpty ? "Your crate fills up as you listen." : "Nothing found.").foregroundStyle(.secondary)
                }
            }.padding()
        }
        .navigationTitle("Library")
        .background(VibeBackground(atmosphere: model.atmosphere))
        .toolbar { ToolbarItem(placement: .primaryAction) {
            Button { showsCrate.toggle() } label: { Image(systemName: showsCrate ? "square.grid.2x2" : "rectangle.stack") }
                .accessibilityLabel(showsCrate ? "Show as grid" : "Show as crate")
        } }
        .searchable(text: $query, prompt: "Search Spotify")
        .onSubmit(of: .search) { reload(resetFocus: true) }
        .onChange(of: kind) { _, _ in reload(resetFocus: true) }
        .onChange(of: query) { _, value in if value.isEmpty { reload(resetFocus: true) } }
        .task(id: model.session?.account.id) { await load() }
        .onChange(of: model.coordinator.libraryFocus) { _, request in
            guard let request else { return }
            kind = request.kind
            reload(resetFocus: true)
        }
        .navigationDestination(item: $browsing) { item in
            if item.kind == .artist { ArtistDetailView(title: item.title, spotifyID: item.spotifyId) }
            else { AlbumDetailView(title: item.title, spotifyID: item.spotifyId, artist: item.subtitle) }
        }
        .sheet(item: $selected) { item in
            VStack(spacing: 14) {
                VStack(spacing: 2) {
                    Text(item.title).font(.headline).lineLimit(2)
                    if let subtitle = item.subtitle { Text(subtitle).font(.subheadline).foregroundStyle(.secondary).lineLimit(1) }
                }.padding(.top, 8)
                Button { selected = nil; Task { await play(item) } } label: { Label("Play now", systemImage: "play.fill").frame(maxWidth: .infinity) }
                    .buttonStyle(.borderedProminent).controlSize(.large)
                Button {
                    selected = nil
                    model.coordinator.openNewStation(.init(start: .records, seeds: [item.seed], feelings: []))
                    model.tab = .radio
                } label: { Label("Start a station from this", systemImage: "dot.radiowaves.left.and.right").frame(maxWidth: .infinity) }
                    .buttonStyle(.bordered).controlSize(.large)
                Button("Cancel", role: .cancel) { selected = nil }
            }
            .padding(.horizontal, 20).padding(.bottom, 12)
            .presentationDetents([.height(260)])
        }
    }

    /// Artists and albums open their own screens; songs offer play / start a station.
    private func open(_ item: Radio.CrateItem) {
        model.recents.record(item)
        focus = 0   // what was just opened is first when the Library comes back; Radio's own plays leave the crate alone
        if item.kind == .track { selected = item } else { browsing = item }
    }

    private func play(_ item: Radio.CrateItem) async {
        guard let token = model.session?.accessToken else { return }
        model.recents.record(item)
        do { _ = try await PlaybackClient().play(token: token, spotifyID: item.spotifyId, kind: "tracks", deviceID: nil) }
        catch { self.error = (error as? LocalizedError)?.errorDescription ?? "Spotify couldn’t play that." }
    }

    /// "Open the album/artist" from the sleeve: search for it and bring it to the front.
    private func applyFocusRequest() {
        guard let request = model.coordinator.libraryFocus, request.kind == kind else { return }
        if let index = items.firstIndex(where: { $0.spotifyId == request.spotifyId }) {
            focus = index
            model.coordinator.libraryFocus = nil
        } else if query != request.title {
            query = request.title
            reload(resetFocus: true)
        } else {
            model.coordinator.libraryFocus = nil
        }
    }

    /// One load at a time: a newer request replaces the one in flight.
    private func reload(resetFocus: Bool) {
        loadTask?.cancel()
        if resetFocus { focus = 0 }
        loadTask = Task { await load() }
    }

    private func load() async {
        guard model.session != nil else { return }
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--uitesting") {
            if let name = ProcessInfo.processInfo.arguments.first(where: { $0.hasPrefix("--uitesting-kind=") })?.dropFirst(17),
               let launchKind = Radio.SeedKind(rawValue: String(name)), launchKind != kind, browsing == nil { kind = launchKind; return }
            // The first record matches the catalog fixtures so browsing (artist -> albums -> tracks) works offline.
            let known: [Radio.SeedKind: (String, String, String?)] = [
                .album: ("1weenld61qoidwYuZ1GESA", "Kind of Blue", "Miles Davis"), .artist: ("0kbYTNQb4Pb1rPbbaF0pT4", "Miles Davis", nil),
                .track: ("0aWMVrwxPNYkKmFthzmpRi", "Blue in Green", "Miles Davis"),
            ]
            fetched = (1...9).map { index in
                if index == 1, let (id, title, subtitle) = known[kind] {
                    return Radio.CrateItem(id: Radio.ID("\(index)"), kind: kind, spotifyId: id, title: title, subtitle: subtitle, artworkUrl: nil, track: nil)
                }
                return Radio.CrateItem(id: Radio.ID("\(index)"), kind: kind, spotifyId: "fixture\(index)", title: "Record \(index)", subtitle: "Fixture artist", artworkUrl: nil, track: nil)
            }
            // `--uitesting-browse` opens the first record's screen (for screenshots).
            if ProcessInfo.processInfo.arguments.contains("--uitesting-browse"), browsing == nil, selected == nil { open(fetched[0]) }
            return
        }
        #endif
        loading = true; error = nil
        defer { if !Task.isCancelled { loading = false } }
        do {
            fetched = try await model.api.crate(kind: kind, query: query)
            fetchedQuery = query
            applyFocusRequest()
        }
        catch is CancellationError { return }
        catch {
            fetched = []; fetchedQuery = query
            // Recent resources still show without the server; only an empty Library reports the failure.
            if !(fetchedQuery.isEmpty && !items.isEmpty) { self.error = (error as? LocalizedError)?.errorDescription ?? "The crate could not be loaded." }
        }
    }
}

private struct CrateCard: View {
    let item: Radio.CrateItem
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            AsyncImage(url: item.artworkURL) { $0.resizable().scaledToFill() } placeholder: {
                ZStack { Color.secondary.opacity(0.14); Image(systemName: item.kind == .artist ? "person.fill" : "music.note").foregroundStyle(.secondary) }
            }
            .aspectRatio(1, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: item.kind == .artist ? 999 : 14, style: .continuous))
            Text(item.title).font(.subheadline.weight(.semibold)).lineLimit(1)
            if let subtitle = item.subtitle { Text(subtitle).font(.caption).foregroundStyle(.secondary).lineLimit(1) }
        }
    }
}
