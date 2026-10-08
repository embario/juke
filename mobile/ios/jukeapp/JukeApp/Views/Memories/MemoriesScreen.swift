import PhotosUI
import SwiftUI
import UIKit

struct MemoriesScreen: View {
    @Environment(VibeAppModel.self) private var model
    @State private var composing = false

    var body: some View {
        let store = model.memories
        List {
            if let error = store.error { Text(error).foregroundStyle(.secondary) }
            Section {
                VStack(alignment: .leading, spacing: 6) {
                    Text("A THOUGHT").font(.caption.bold()).tracking(1.4).foregroundStyle(model.atmosphere.primary)
                    Text(store.insights.question).font(.title3.weight(.semibold))
                    ForEach(store.insights.connections.prefix(3)) { connection in
                        Label("\(connection.label) · \(connection.count)", systemImage: connection.kind == "person" ? "person" : "link").font(.footnote).foregroundStyle(.secondary)
                    }
                }.padding(.vertical, 4)
            }
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
    @Environment(VibeAppModel.self) private var model
    let memory: MusicMemory
    @State private var newTag = ""
    @State private var error: String?

    private var current: MusicMemory { model.memories.memories.first { $0.id == memory.id } ?? memory }

    var body: some View {
        List {
            if !current.media.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack { ForEach(current.media) { MemoryMediaThumb(media: $0) } }
                }.listRowInsets(EdgeInsets())
            }
            if !current.text.isEmpty { Text(current.text) }
            if !current.place.isEmpty { LabeledContent("Place", value: current.place) }
            if !current.people.isEmpty { LabeledContent("With", value: current.people.joined(separator: ", ")) }
            ForEach(current.songs) { song in
                Label {
                    VStack(alignment: .leading) { Text(song.title); Text(song.artist).font(.caption).foregroundStyle(.secondary)
                        if let segment = song.segmentDescription { Text(segment).font(.caption2).foregroundStyle(.tertiary) } }
                } icon: { Image(systemName: "music.note") }
                .swipeActions { Button("Play") { Task { await model.memoryPlayer.play(song) } }.tint(.accentColor) }
                .overlay(alignment: .trailing) {
                    Button { Task { await model.memoryPlayer.play(song) } } label: {
                        Label(song.segmentDescription == nil ? "Play" : "Play the moment", systemImage: "play.fill").labelStyle(.iconOnly)
                    }
                    .buttonStyle(.borderless)
                    .disabled(model.memoryPlayer.isBusy)
                    .accessibilityLabel(song.segmentDescription == nil ? "Play \(song.title)" : "Play the moment")
                    .accessibilityIdentifier("memory.playMoment")
                }
            }
            if let message = model.memoryPlayer.message { Text(message).font(.footnote).foregroundStyle(.secondary) }
            Section("Tags") {
                ForEach(current.tags, id: \.self) { tag in
                    HStack { Text("#\(tag)"); Spacer()
                        Button { Task { await setTags(current.tags.filter { $0 != tag }) } } label: { Image(systemName: "minus.circle") }.buttonStyle(.plain)
                            .accessibilityLabel("Remove \(tag)")
                    }
                }
                HStack {
                    TextField("Add a tag", text: $newTag).onSubmit(addTag)
                    Button("Add", action: addTag).disabled(newTag.trimmingCharacters(in: .whitespaces).isEmpty)
                }
                if !current.generatedTags.isEmpty {
                    Text("Suggested: " + current.generatedTags.map { "#\($0)" }.joined(separator: " ")).font(.footnote).foregroundStyle(.secondary)
                }
                if let error { Text(error).font(.footnote).foregroundStyle(.red) }
            }
        }.navigationTitle(current.displayTitle).navigationBarTitleDisplayMode(.inline)
    }

    private func addTag() {
        let tag = newTag; newTag = ""
        Task { await setTags(current.tags + [tag]) }
    }

    private func setTags(_ tags: [String]) async {
        do { try await model.memories.updateTags(tags, for: current); error = nil }
        catch { self.error = error.localizedDescription }
    }
}

private struct MemoryMediaThumb: View {
    @Environment(VibeAppModel.self) private var model
    let media: MemoryMedia
    @State private var image: UIImage?
    @State private var failed = false

    var body: some View {
        ZStack {
            Color.secondary.opacity(0.15)
            if let image { Image(uiImage: image).resizable().scaledToFill() }
            else if failed || media.kind != "image" { Image(systemName: media.kind == "video" ? "play.rectangle" : "photo").foregroundStyle(.secondary) }
            else { ProgressView() }
        }
        .frame(width: 160, height: 160).clipShape(RoundedRectangle(cornerRadius: 12))
        .task {
            guard media.kind == "image" else { return }
            do { let url = try await model.memories.localMediaURL(media); image = UIImage(contentsOfFile: url.path) }
            catch { failed = true }
        }
        .accessibilityLabel(media.kind == "video" ? "Video attachment" : "Photo attachment")
    }
}

struct MemoryComposer: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var draft = MemoryDraft()
    @State private var songTitle = ""
    @State private var songArtist = ""
    @State private var people = ""
    @State private var picks: [PhotosPickerItem] = []
    @State private var attached: [MemoryMedia] = []
    @State private var uploading = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section { TextField("Title", text: $draft.title); DatePicker("When", selection: $draft.occurredAt, displayedComponents: .date) }
                Section("The moment") { TextField("What was happening? Use #tags", text: $draft.text, axis: .vertical).lineLimit(3...8) }
                Section("A song") {
                    TextField("Song title", text: $songTitle); TextField("Artist", text: $songArtist)
                    if let track = model.radio.track, model.radio.isOnAir {
                        Button("Use \(track.title)", systemImage: "dot.radiowaves.left.and.right") { songTitle = track.title; songArtist = track.artist }
                    }
                }
                Section("Photos and videos") {
                    PhotosPicker(selection: $picks, maxSelectionCount: 6, matching: .any(of: [.images, .videos])) {
                        Label(attached.isEmpty ? "Add photos or videos" : "\(attached.count) attached", systemImage: "photo.badge.plus")
                    }
                    if uploading { ProgressView() }
                }
                Section("Who and where") { TextField("People (comma separated)", text: $people); TextField("Place", text: $draft.place) }
                if !model.memories.reusableTags.isEmpty {
                    Section("Your tags") {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack { ForEach(model.memories.reusableTags.prefix(20), id: \.self) { tag in
                                Button("#\(tag)") { draft.tags = MemoryDraft.normalizedTags(draft.tags + [tag]) }.buttonStyle(.bordered).controlSize(.small)
                            } }
                        }
                    }
                }
                if let error { Section { Text(error).foregroundStyle(.red) } }
            }
            .navigationTitle("New memory").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { Task { await model.memories.discardMedia(attached); dismiss() } } }
                ToolbarItem(placement: .confirmationAction) { Button("Save") { Task { await save() } }.disabled(model.memories.isSaving || uploading) }
            }
            .onChange(of: picks) { _, items in Task { await upload(items) } }
        }
    }

    private func upload(_ items: [PhotosPickerItem]) async {
        guard !items.isEmpty else { return }
        uploading = true; error = nil
        defer { uploading = false; picks = [] }
        for item in items {
            do {
                guard let data = try await item.loadTransferable(type: Data.self) else { continue }
                let type = item.supportedContentTypes.first
                let ext = type?.preferredFilenameExtension ?? "jpg"
                let media = try await model.memories.upload(data, filename: "memory-\(UUID().uuidString.prefix(8)).\(ext)", contentType: type?.preferredMIMEType ?? "image/jpeg")
                attached.append(media)
            } catch { self.error = (error as? LocalizedError)?.errorDescription ?? "That attachment could not be added." }
        }
    }

    private func save() async {
        var value = draft
        value.mediaIDs = attached.map(\.id)
        value.people = people.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        value.tags = MemoryDraft.normalizedTags(value.tags + MemoryDraft.storyTags(value.text))
        if !songTitle.trimmingCharacters(in: .whitespaces).isEmpty {
            value.songs = [MemorySong(title: songTitle, artist: songArtist, provider: "manual")]
        }
        if let message = value.validationMessage { error = message; return }
        do { _ = try await model.memories.save(value); dismiss() }
        catch { self.error = error.localizedDescription }
    }
}
