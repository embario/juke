import SwiftUI

/// The crate on iPhone: the listener's personal crate, or Spotify search when a query is typed.
struct LibraryScreen: View {
    @Environment(VibeAppModel.self) private var model
    @State private var kind: Radio.SeedKind = .track
    @State private var query = ""
    @State private var items: [Radio.CrateItem] = []
    @State private var loading = false
    @State private var error: String?
    @State private var selected: Radio.CrateItem?
    @State private var focus = 0
    @AppStorage("juke.library.crateView") private var showsCrate = true
    @AppStorage("juke.settings.crateFlipDirection") private var flipRaw = CrateFlipDirection.sideToSide.rawValue

    private let columns = [GridItem(.adaptive(minimum: 150), spacing: 14)]

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
                    CrateView(items: items, mode: CrateMode(CrateFlipDirection(rawValue: flipRaw) ?? .sideToSide), onSelect: { selected = $0 }, focus: $focus)
                    if items.indices.contains(focus) {
                        VStack(spacing: 2) {
                            Text(items[focus].title).font(.headline).lineLimit(1)
                            if let subtitle = items[focus].subtitle { Text(subtitle).font(.subheadline).foregroundStyle(.secondary).lineLimit(1) }
                        }.frame(maxWidth: .infinity)
                    }
                } else {
                    LazyVGrid(columns: columns, spacing: 14) {
                        ForEach(items) { item in
                            Button { selected = item } label: { CrateCard(item: item) }.buttonStyle(.plain)
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
        .onSubmit(of: .search) { Task { await load() } }
        .onChange(of: kind) { _, _ in Task { await load() } }
        .onChange(of: query) { _, value in if value.isEmpty { Task { await load() } } }
        .task(id: model.session?.account.id) { await load() }
        .onChange(of: model.coordinator.libraryFocus) { _, request in
            guard let request else { return }
            kind = request.kind
            Task { await load() }
        }
        .confirmationDialog(selected?.title ?? "", isPresented: Binding(get: { selected != nil }, set: { if !$0 { selected = nil } }), presenting: selected) { item in
            Button("Start a station from this") {
                model.coordinator.openNewStation(.init(start: .records, seeds: [item.seed], feelings: []))
                model.tab = .radio
            }
        } message: { Text($0.subtitle ?? "") }
    }

    /// "Open the album/artist" from the sleeve: search for it and bring it to the front.
    private func applyFocusRequest() {
        guard let request = model.coordinator.libraryFocus, request.kind == kind else { return }
        if let index = items.firstIndex(where: { $0.spotifyId == request.spotifyId }) {
            focus = index
            model.coordinator.libraryFocus = nil
        } else if query != request.title {
            query = request.title
            Task { await load() }
        } else {
            model.coordinator.libraryFocus = nil
        }
    }

    private func load() async {
        guard model.session != nil else { return }
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--uitesting") {
            items = (1...9).map { Radio.CrateItem(id: Radio.ID("\($0)"), kind: kind, spotifyId: "fixture\($0)", title: "Record \($0)", subtitle: "Fixture artist", artworkUrl: nil, track: nil) }
            return
        }
        #endif
        loading = true; error = nil
        defer { loading = false }
        do {
            items = try await model.api.crate(kind: kind, query: query)
            focus = CrateLayout.clamp(focus, count: items.count)
            applyFocusRequest()
        }
        catch is CancellationError { return }
        catch { items = []; self.error = (error as? LocalizedError)?.errorDescription ?? "The crate could not be loaded." }
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
