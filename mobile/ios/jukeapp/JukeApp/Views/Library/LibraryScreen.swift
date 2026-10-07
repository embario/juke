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
                LazyVGrid(columns: columns, spacing: 14) {
                    ForEach(items) { item in
                        Button { selected = item } label: { CrateCard(item: item) }.buttonStyle(.plain)
                    }
                }
                if !loading, items.isEmpty, error == nil {
                    Text(query.isEmpty ? "Your crate fills up as you listen." : "Nothing found.").foregroundStyle(.secondary)
                }
            }.padding()
        }
        .navigationTitle("Library")
        .background(VibeBackground(atmosphere: model.atmosphere))
        .searchable(text: $query, prompt: "Search Spotify")
        .onSubmit(of: .search) { Task { await load() } }
        .onChange(of: kind) { _, _ in Task { await load() } }
        .onChange(of: query) { _, value in if value.isEmpty { Task { await load() } } }
        .task(id: model.session?.account.id) { await load() }
        .confirmationDialog(selected?.title ?? "", isPresented: Binding(get: { selected != nil }, set: { if !$0 { selected = nil } }), presenting: selected) { item in
            Button("Start a station from this") {
                model.coordinator.openNewStation(.init(start: .records, seeds: [item.seed], feelings: []))
                model.tab = .radio
            }
        } message: { Text($0.subtitle ?? "") }
    }

    private func load() async {
        guard model.session != nil else { return }
        loading = true; error = nil
        defer { loading = false }
        do { items = try await model.api.crate(kind: kind, query: query) }
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
