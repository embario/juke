import SwiftUI

struct MemoriesScreen: View {
    @Environment(VibeAppModel.self) private var model
    @State private var composing = false

    var body: some View {
        let store = model.memories
        List {
            if let error = store.error { Text(error).foregroundStyle(.secondary) }
            if store.memories.isEmpty, !store.isLoading {
                ContentUnavailableView("No memories yet", systemImage: "photo.on.rectangle.angled", description: Text("Save a song with the moment it belongs to."))
            }
            ForEach(store.memories) { memory in
                NavigationLink { MemoryDetail(memory: memory) } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(memory.displayTitle).font(.headline).lineLimit(1)
                        Text(memory.occurredAt.formatted(date: .abbreviated, time: .omitted)).font(.caption).foregroundStyle(.secondary)
                        if let song = memory.songs.first { Label("\(song.title) — \(song.artist)", systemImage: "music.note").font(.subheadline).lineLimit(1) }
                    }
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background(VibeBackground(atmosphere: model.atmosphere))
        .navigationTitle("Memories")
        .toolbar { ToolbarItem(placement: .primaryAction) { Button { composing = true } label: { Image(systemName: "plus") }.accessibilityLabel("New memory") } }
        .refreshable { await store.refresh() }
        .task(id: model.session?.account.id) { await store.refresh() }
        .overlay { if store.isLoading, store.memories.isEmpty { ProgressView() } }
        .sheet(isPresented: $composing) { MemoryComposer() }
    }
}

private struct MemoryDetail: View {
    let memory: MusicMemory
    var body: some View {
        List {
            if !memory.text.isEmpty { Text(memory.text) }
            if !memory.place.isEmpty { LabeledContent("Place", value: memory.place) }
            if !memory.people.isEmpty { LabeledContent("With", value: memory.people.joined(separator: ", ")) }
            ForEach(memory.songs) { song in Label("\(song.title) — \(song.artist)", systemImage: "music.note") }
            if !(memory.tags + memory.generatedTags).isEmpty { Text((memory.tags + memory.generatedTags).map { "#\($0)" }.joined(separator: "  ")).foregroundStyle(.secondary) }
        }.navigationTitle(memory.displayTitle).navigationBarTitleDisplayMode(.inline)
    }
}

struct MemoryComposer: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var draft = MemoryDraft()
    @State private var songTitle = ""
    @State private var songArtist = ""
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section { TextField("Title", text: $draft.title); DatePicker("When", selection: $draft.occurredAt, displayedComponents: .date) }
                Section("The moment") { TextField("What was happening? Use #tags", text: $draft.text, axis: .vertical).lineLimit(3...8) }
                Section("A song") { TextField("Song title", text: $songTitle); TextField("Artist", text: $songArtist) }
                Section { TextField("Place", text: $draft.place) }
                if let error { Section { Text(error).foregroundStyle(.red) } }
            }
            .navigationTitle("New memory").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Save") { Task { await save() } }.disabled(model.memories.isSaving) }
            }
        }
    }

    private func save() async {
        var value = draft
        value.tags = MemoryDraft.normalizedTags(value.tags + MemoryDraft.storyTags(value.text))
        if !songTitle.trimmingCharacters(in: .whitespaces).isEmpty {
            value.songs = [MemorySong(title: songTitle, artist: songArtist, provider: "manual")]
        }
        if let message = value.validationMessage { error = message; return }
        do { _ = try await model.memories.save(value); dismiss() }
        catch { self.error = error.localizedDescription }
    }
}
