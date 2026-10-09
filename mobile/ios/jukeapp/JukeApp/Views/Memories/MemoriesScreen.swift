import PhotosUI
import SwiftUI
import UIKit

struct MemoriesScreen: View {
    @Environment(VibeAppModel.self) private var model
    @State private var composing = false
    @State private var detailID: UUID?
    @State private var memoryToDelete: MusicMemory?
    @State private var showingDeleteConfirmation = false

    var body: some View {
        let store = model.memories
        ScrollView {
            VStack(spacing: 0) {
                if let error = store.error { Text(error).font(.footnote).foregroundStyle(.secondary).padding(.horizontal) }
                if store.memories.isEmpty {
                    if !store.isLoading {
                        ContentUnavailableView {
                            Label("No memories yet", systemImage: "photo.on.rectangle.angled")
                        } description: {
                            Text("Save a song with the moment it belongs to.")
                        } actions: {
                            Button("New memory") { composing = true }.buttonStyle(.borderedProminent)
                                .accessibilityIdentifier("memory.empty.new")
                        }
                        .frame(maxWidth: .infinity, minHeight: 420)
                    }
                } else {
                    MemoryDeckView(
                        memories: store.memories, question: store.insights.question,
                        open: { detailID = $0.id },
                        delete: { memoryToDelete = $0; showingDeleteConfirmation = true }
                    )
                    .containerRelativeFrame(.vertical, alignment: .center)
                }
            }
        }
        .background(VibeBackground(atmosphere: model.atmosphere))
        .navigationTitle("Memories")
        .toolbar { ToolbarItem(placement: .primaryAction) { Button { composing = true } label: { Image(systemName: "plus") }.accessibilityLabel("New memory") } }
        .confirmationDialog("Delete this memory?", isPresented: $showingDeleteConfirmation, titleVisibility: .visible) {
            Button("Delete Memory", role: .destructive) {
                guard let memoryToDelete else { return }
                Task {
                    do {
                        try await store.delete(memoryToDelete)
                        if detailID == memoryToDelete.id { detailID = nil }
                        self.memoryToDelete = nil
                    } catch {
                        store.error = error.localizedDescription
                    }
                }
            }
            Button("Cancel", role: .cancel) { memoryToDelete = nil }
        } message: {
            if let memoryToDelete { Text("\(memoryToDelete.displayTitle) will be permanently deleted.") }
        }
        .refreshable { await store.refresh() }
        .task(id: model.session?.account.id) {
            await store.refresh()
            #if DEBUG
            // `--uitesting-memory-detail=N` opens the Nth memory (for screenshots).
            if let value = ProcessInfo.processInfo.arguments.first(where: { $0.hasPrefix("--uitesting-memory-detail=") })?.dropFirst(26), let index = Int(value) {
                for _ in 0..<60 where store.memories.count <= index { try? await Task.sleep(for: .milliseconds(100)) }
                if store.memories.indices.contains(index) { detailID = store.memories[index].id }
            }
            #endif
        }
        .navigationDestination(item: $detailID) { id in if let memory = store.memories.first(where: { $0.id == id }) { MemoryDetail(memory: memory) } }
        .overlay { if store.isLoading, store.memories.isEmpty { ProgressView() } }
        #if DEBUG
        .onAppear { if ProcessInfo.processInfo.arguments.contains(where: { $0.hasPrefix("--uitesting-memory-step=") }) { composing = true } }
        #endif
        .fullScreenCover(isPresented: $composing) { MemoryJourneyView(startWithSong: model.radio.isOnAir || model.nowPlaying.isPlaying) { composing = false } }
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
                } icon: {
                    AsyncImage(url: song.artworkURL) { $0.resizable().scaledToFill() } placeholder: { Image(systemName: "music.note") }
                        .frame(width: 40, height: 40).clipShape(RoundedRectangle(cornerRadius: 6))
                }
                .swipeActions { Button("Play") { Task { await model.memoryPlayer.play(song, in: current.id) } }.tint(.accentColor) }
                .overlay(alignment: .trailing) {
                    Button { Task { await model.memoryPlayer.play(song, in: current.id) } } label: {
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
            else if failed || (media.kind != "image" && media.kind != "video") { Image(systemName: media.kind == "video" ? "play.rectangle" : "photo").foregroundStyle(.secondary) }
            else { ProgressView() }
        }
        .frame(width: 160, height: 160).clipShape(RoundedRectangle(cornerRadius: 12))
        .task {
            do {
                let url = try await model.memories.localMediaURL(media)
                image = media.kind == "video" ? await MemoryImageDecoder.videoFrame(url, maxPixel: 480) : MemoryImageDecoder.downsampled(url, maxPixel: 960)
                if image == nil { failed = true }
            } catch { failed = true }
        }
        .accessibilityLabel(media.kind == "video" ? "Video attachment" : "Photo attachment")
    }
}
