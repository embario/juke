import SwiftUI

struct DiscoverView: View {
    @Environment(VibeAppModel.self) private var model
    @State private var query = ""
    @State private var kind = "tracks"
    @State private var results: [CatalogItem] = []
    @State private var isSearching = false
    private let api = VibeAPI()

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                Text("Follow a sound").font(.largeTitle.bold())
                Text("Search Juke's connected catalog and carry anything interesting into the conversation.").foregroundStyle(.secondary)
                Picker("Type", selection: $kind) { Text("Songs").tag("tracks"); Text("Artists").tag("artists"); Text("Albums").tag("albums") }.pickerStyle(.segmented)
                HStack { TextField("Search music", text: $query).textFieldStyle(.roundedBorder).submitLabel(.search).onSubmit { search() }; Button { search() } label: { Image(systemName: "magnifyingglass") }.buttonStyle(.borderedProminent).tint(model.atmosphere.primary) }
                if isSearching { ProgressView().frame(maxWidth: .infinity) }
                ForEach(results) { item in
                    HStack(spacing: 14) {
                        AsyncImage(url: item.artworkURL) { $0.resizable().scaledToFill() } placeholder: { Color.secondary.opacity(0.12).overlay(Image(systemName: "music.note")) }.frame(width: 68, height: 68).clipShape(RoundedRectangle(cornerRadius: 12))
                        VStack(alignment: .leading) { Text(item.name).font(.headline); Text(item.subtitle).font(.caption).foregroundStyle(.secondary); Button("Ask Juke about this") { model.draft = "Help me explore \(item.name) by \(item.subtitle)." }.font(.caption.bold()).foregroundStyle(model.atmosphere.primary) }
                        Spacer()
                    }.padding(10).background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16))
                }
            }.padding()
        }.navigationTitle("Discover")
    }

    private func search() {
        guard let token = model.session?.accessToken, !query.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        isSearching = true
        Task { do { results = try await api.search(query, kind: kind, token: token) } catch { model.errorMessage = error.localizedDescription }; isSearching = false }
    }
}
