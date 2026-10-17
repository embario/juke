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
        GeometryReader { screen in
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
                            memories: store.memories, question: store.insights.question, minHeight: screen.size.height,
                            open: { detailID = $0.id },
                            delete: { memoryToDelete = $0; showingDeleteConfirmation = true }
                        )
                    }
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
