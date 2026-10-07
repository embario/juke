import SwiftUI

/// Build a station from records (seeds) and feelings, then tune to it.
struct NewStationScreen: View {
    @Environment(VibeAppModel.self) private var model
    @State var draft: JukeCoordinator.NewStationDraft
    @State private var name = ""
    @State private var query = ""
    @State private var kind: Radio.SeedKind = .track
    @State private var results: [Radio.CrateItem] = []
    @State private var feeling = ""
    @State private var saving = false
    @State private var error: String?

    static let maxSeeds = 5

    init(draft: JukeCoordinator.NewStationDraft) { _draft = State(initialValue: draft) }

    private var canCreate: Bool { !(draft.seeds.isEmpty && draft.feelings.isEmpty) && !saving }

    var body: some View {
        Form {
            Section("Name (optional)") { TextField("My late-night station", text: $name) }
            Section("Records") {
                ForEach(draft.seeds) { seed in
                    HStack { Text(seed.title); Spacer(); Text(seed.subtitle ?? "").font(.caption).foregroundStyle(.secondary)
                        Button { draft.seeds.removeAll { $0.id == seed.id } } label: { Image(systemName: "xmark.circle.fill") }.buttonStyle(.plain)
                    }
                }
                Picker("Type", selection: $kind) {
                    Text("Songs").tag(Radio.SeedKind.track); Text("Artists").tag(Radio.SeedKind.artist); Text("Albums").tag(Radio.SeedKind.album)
                }.pickerStyle(.segmented)
                TextField("Search for a record", text: $query).submitLabel(.search).onSubmit { Task { await search() } }
                ForEach(results.prefix(8)) { item in
                    Button { add(item.seed) } label: {
                        HStack { Text(item.title); Spacer(); Text(item.subtitle ?? "").font(.caption).foregroundStyle(.secondary) }
                    }.disabled(draft.seeds.count >= Self.maxSeeds)
                }
            }
            Section("Feelings") {
                ForEach(draft.feelings, id: \.self) { value in
                    HStack { Text(value); Spacer(); Button { draft.feelings.removeAll { $0 == value } } label: { Image(systemName: "xmark.circle.fill") }.buttonStyle(.plain) }
                }
                TextField("An emoji or a few words", text: $feeling).onSubmit(addFeeling)
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack { ForEach(RadioController.pickerEmoji, id: \.self) { emoji in
                        Button(emoji) { if !draft.feelings.contains(emoji) { draft.feelings.append(emoji) } }.font(.title2)
                    } }
                }
            }
            if let error { Section { Text(error).foregroundStyle(.red) } }
            Section {
                Button("Create and tune after this song") { Task { await create(.afterCurrentSong) } }
                Button("Create and play now") { Task { await create(.now) } }
            }.disabled(!canCreate)
        }
        .scrollContentBackground(.hidden)
        .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { model.coordinator.closeNewStation() } } }
        .task { if draft.start == .records, !query.isEmpty { await search() } }
        .onChange(of: kind) { _, _ in if !query.isEmpty { Task { await search() } } }
    }

    private func add(_ seed: Radio.Seed) {
        if !draft.seeds.contains(where: { $0.id == seed.id }) { draft.seeds.append(seed) }
    }

    private func addFeeling() {
        let text = feeling.trimmingCharacters(in: .whitespacesAndNewlines)
        feeling = ""
        guard !text.isEmpty, text.count <= Radio.ReactionsRequest.maxPhraseLength, !draft.feelings.contains(text) else { return }
        draft.feelings.append(text)
    }

    private func search() async {
        do { results = try await model.api.crate(kind: kind, query: query) }
        catch is CancellationError { return }
        catch { self.error = (error as? LocalizedError)?.errorDescription }
    }

    private func create(_ timing: JukeCoordinator.StationRequest.Timing) async {
        addFeeling()
        saving = true; error = nil
        defer { saving = false }
        do {
            let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
            let station = try await model.api.createStation(name: trimmed.isEmpty ? nil : trimmed, seeds: draft.seeds, feelings: draft.feelings)
            await model.radio.loadStations()
            model.coordinator.requestStation(station.id, timing: timing)
        } catch { self.error = (error as? LocalizedError)?.errorDescription ?? "The station could not be created." }
    }
}
