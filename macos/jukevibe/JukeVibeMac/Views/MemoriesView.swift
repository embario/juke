import SwiftUI
import AVKit

struct MemoriesView: View {
    @Environment(AppModel.self) private var app
    @Environment(MemoryStore.self) private var store
    @State private var isComposing = false
    @State private var selection: UUID?
    @State private var search = ""
    @State private var connection: MemoryInsights.Connection?
    @State private var oldestFirst = false
    @State private var composerStartsWithSong = false

    private var filtered: [MusicMemory] {
        store.memories.filter { memory in
            (connection == nil || connection!.memoryIDs.contains(memory.id)) &&
            (search.isEmpty || ([memory.title, memory.text, memory.place] + memory.tags + memory.people + memory.songs.map { "\($0.title) \($0.artist)" }).joined(separator: " ").localizedCaseInsensitiveContains(search))
        }.sorted { oldestFirst ? $0.occurredAt < $1.occurredAt : $0.occurredAt > $1.occurredAt }
    }

    var body: some View {
        Group {
            if isComposing {
                MemoryComposerView(startWithSong: composerStartsWithSong, onSaved: { selection = $0; isComposing = false }, onClose: { isComposing = false })
            } else { catalog }
        }
        .onChange(of: isComposing) { _, composing in
            if composing { composerStartsWithSong = app.detection.track != nil }
            app.memoryJourneyActive = composing
        }
        .onDisappear { app.memoryJourneyActive = false }
    }

    private var catalog: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                header
                if let error = store.error {
                    HStack { Label(error, systemImage: "wifi.exclamationmark"); Spacer(); Button("Try again") { Task { await store.refresh() } } }
                        .font(.callout).padding().background(.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 14))
                }
                if let selected = store.memories.first(where: { $0.id == selection }) {
                    Button { selection = nil } label: { Label("All memories", systemImage: "arrow.left") }.buttonStyle(.plain)
                    MemoryDetailView(memory: selected)
                } else {
                    invitation
                    if search.isEmpty && connection == nil && !onThisDay.isEmpty { onThisDaySection }
                    if !store.insights.connections.isEmpty { connections }
                    HStack {
                        Text("Your soundtrack, remembered").font(.title2.weight(.semibold))
                        Spacer()
                        Text("\(filtered.count) memories").foregroundStyle(.secondary)
                        Toggle("Oldest first", isOn: $oldestFirst).toggleStyle(.checkbox)
                    }
                    HStack {
                        Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                        TextField("Find a song, person, place, or tag", text: $search).textFieldStyle(.plain)
                        if let connection { Button("\(connection.label) ×") { self.connection = nil } }
                    }.padding(12).background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 12))
                    if store.isLoading && store.memories.isEmpty { ProgressView("Opening your memories…").frame(maxWidth: .infinity).padding(40) }
                    else if filtered.isEmpty {
                        ContentUnavailableView {
                            Label(store.memories.isEmpty ? "A song can hold a whole story." : "No memories found", systemImage: "photo.on.rectangle.angled")
                        } description: {
                            Text(store.memories.isEmpty ? "Save a song, a face, a place—or just a few words. Start wherever the memory begins." : "Try another word or clear the connection filter.")
                        } actions: {
                            if store.memories.isEmpty { Button("Create your first memory") { isComposing = true }.buttonStyle(.borderedProminent) }
                        }.padding(.vertical, 25)
                    } else {
                        timeline
                    }
                }
            }.padding(30).frame(maxWidth: 1250, alignment: .leading).frame(maxWidth: .infinity)
        }
        .accessibilityIdentifier("memory.catalog")

    }

    /// Journal-style chapters: one section per month, with the year announced when it changes.
    private var timeline: some View {
        let calendar = Calendar.current
        let months = Dictionary(grouping: filtered) { calendar.dateInterval(of: .month, for: $0.occurredAt)?.start ?? $0.occurredAt }
        let keys = months.keys.sorted { oldestFirst ? $0 < $1 : $0 > $1 }
        return LazyVStack(alignment: .leading, spacing: 28) {
            ForEach(Array(keys.enumerated()), id: \.element) { index, month in
                let year = calendar.component(.year, from: month)
                VStack(alignment: .leading, spacing: 14) {
                    if index == 0 || calendar.component(.year, from: keys[index - 1]) != year {
                        Text(String(year)).font(.system(size: 30, weight: .bold, design: .rounded)).monospacedDigit().padding(.top, index == 0 ? 0 : 14)
                    }
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Text(month.formatted(.dateTime.month(.wide))).font(.title3.weight(.semibold))
                        Text("\(months[month]?.count ?? 0)").font(.caption).foregroundStyle(.secondary)
                        Rectangle().fill(.primary.opacity(0.08)).frame(height: 1)
                    }
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 280), alignment: .top)], alignment: .leading, spacing: 20) {
                        ForEach(months[month] ?? []) { memory in
                            Button { selection = memory.id } label: { MemoryCard(memory: memory) }
                                .buttonStyle(.plain).accessibilityIdentifier("memory.card.\(memory.title)")
                        }
                    }
                }
            }
        }
    }

    /// Memories from this week in earlier years, resurfaced like a journal falling open.
    private var onThisDay: [MusicMemory] {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        let thisYear = calendar.component(.year, from: today)
        return store.memories.filter { memory in
            let years = thisYear - calendar.component(.year, from: memory.occurredAt)
            guard years > 0, let anniversary = calendar.date(byAdding: .year, value: years, to: calendar.startOfDay(for: memory.occurredAt)) else { return false }
            return abs(calendar.dateComponents([.day], from: today, to: anniversary).day ?? 99) <= 3
        }.sorted { $0.occurredAt > $1.occurredAt }
    }

    private var onThisDaySection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("On this day", systemImage: "clock.arrow.circlepath").font(.headline)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 16) {
                    ForEach(onThisDay) { memory in
                        let years = Calendar.current.component(.year, from: Date()) - Calendar.current.component(.year, from: memory.occurredAt)
                        Button { selection = memory.id } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                Text(years == 1 ? "A year ago" : "\(years) years ago").font(.caption.weight(.bold)).tracking(1).foregroundStyle(.orange)
                                MemoryCard(memory: memory)
                            }.frame(width: 280)
                        }.buttonStyle(.plain).accessibilityIdentifier("memory.onThisDay.\(memory.id)")
                    }
                }
            }
        }
    }

    private var header: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 5) {
                Text("JUKE VIBE · YOUR MUSIC MEMORIES").font(.caption.weight(.bold)).tracking(2).foregroundStyle(.secondary)
                Text("Your life has a soundtrack.").font(.system(size: 38, weight: .bold, design: .rounded))
            }
            Spacer()
            Button { Task { await store.refresh() } } label: { Image(systemName: "arrow.clockwise") }.help("Refresh memories")
            Button { isComposing = true } label: { Label("New memory", systemImage: "plus") }
                .buttonStyle(.borderedProminent).controlSize(.large).tint(.accentColor).accessibilityIdentifier("memory.new")
        }
    }

    private var invitation: some View {
        HStack(spacing: 24) {
            Image(systemName: "sparkles").font(.system(size: 32)).foregroundStyle(.orange)
            VStack(alignment: .leading, spacing: 10) {
                Text("A LITTLE NUDGE").font(.caption.weight(.bold)).tracking(2).foregroundStyle(.secondary)
                Text(store.insights.question).font(.title2.weight(.medium)).fixedSize(horizontal: false, vertical: true)
                if let track = app.detection.track {
                    Label("Listening to \(track.title) · \(track.artist)", systemImage: "waveform").foregroundStyle(.secondary)
                }
                Button("This brings something back") { isComposing = true }.buttonStyle(.link)
            }
            Spacer(minLength: 0)
        }.padding(26).frame(maxWidth: .infinity, alignment: .leading)
            .background(LinearGradient(colors: [.orange.opacity(0.13), .pink.opacity(0.09), .purple.opacity(0.08)], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 24))
    }

    private var connections: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Threads through your memories").font(.headline)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack {
                    ForEach(store.insights.connections) { item in
                        Button { connection = item } label: {
                            Label("\(item.label) · \(item.count)", systemImage: item.kind == "person" ? "person.2" : item.kind == "place" ? "mappin" : "music.note")
                        }.buttonStyle(.bordered)
                    }
                }
            }
        }
    }
}

private struct MemoryCard: View {
    let memory: MusicMemory
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let media = memory.media.first { MemoryMediaView(media: media, compact: true).frame(height: 175).clipped() }
            else {
                ZStack(alignment: .bottomLeading) {
                    LinearGradient(colors: [.indigo.opacity(0.4), .pink.opacity(0.2), .orange.opacity(0.25)], startPoint: .topLeading, endPoint: .bottomTrailing)
                    Image(systemName: memory.songs.isEmpty ? "quote.opening" : "waveform").font(.system(size: 54, weight: .light)).padding(22).foregroundStyle(.primary.opacity(0.6))
                }.frame(height: 135)
            }
            VStack(alignment: .leading, spacing: 9) {
                Text(memory.occurredAt.formatted(date: .abbreviated, time: .omitted)).font(.caption).foregroundStyle(.secondary)
                if !memory.title.isEmpty || !memory.songs.isEmpty { Text(memory.displayTitle).font(.title3.weight(.semibold)).lineLimit(2) }
                if !memory.text.isEmpty { Text(memory.text).font(memory.songs.isEmpty && memory.title.isEmpty ? .title3 : .body).lineLimit(4) }
                if let song = memory.songs.first { Label("\(song.title) · \(song.artist)", systemImage: "music.note").font(.callout).lineLimit(1) }
                HStack {
                    if !memory.place.isEmpty { Label(memory.place, systemImage: "mappin").lineLimit(1) }
                    Spacer()
                    if !memory.media.isEmpty { Label("\(memory.media.count)", systemImage: "photo.on.rectangle") }
                }.font(.caption).foregroundStyle(.secondary)
                if !memory.tags.isEmpty { Text(memory.tags.prefix(4).map { "#\($0)" }.joined(separator: "  ")).font(.caption).foregroundStyle(.secondary).lineLimit(1) }
            }.padding([.horizontal, .bottom], 18)
        }.frame(maxWidth: .infinity, alignment: .leading)
            .background(.background.opacity(0.75), in: RoundedRectangle(cornerRadius: 20))
            .clipShape(RoundedRectangle(cornerRadius: 20))
            .overlay(RoundedRectangle(cornerRadius: 20).stroke(.primary.opacity(0.08)))
            .contentShape(RoundedRectangle(cornerRadius: 20))
    }
}

struct MemoryDetailView: View {
    @Environment(AppModel.self) private var app
    @Environment(MemoryStore.self) private var store
    let memory: MusicMemory
    @State private var editingTags = false
    @State private var tagsText = ""
    @State private var error: String?
    @State private var saving = false

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            Text(memory.occurredAt.formatted(date: .long, time: .omitted)).foregroundStyle(.secondary)
            if !memory.title.isEmpty || !memory.songs.isEmpty { Text(memory.displayTitle).font(.system(size: 34, weight: .bold, design: .rounded)) }
            if !memory.text.isEmpty { Text(memory.text).font(.title3).textSelection(.enabled).lineSpacing(5) }
            HStack(spacing: 18) {
                if !memory.place.isEmpty { Label(memory.place, systemImage: "mappin.and.ellipse") }
                if !memory.people.isEmpty { Label(memory.people.joined(separator: ", "), systemImage: "person.2") }
            }.foregroundStyle(.secondary)
            if !memory.media.isEmpty {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 280))], spacing: 16) {
                    ForEach(memory.media) { media in MemoryMediaView(media: media, compact: false).frame(height: 260).clipShape(RoundedRectangle(cornerRadius: 16)) }
                }
            }
            ForEach(memory.songs) { song in
                HStack(spacing: 14) {
                    Image(systemName: "music.note").font(.title2).frame(width: 48, height: 48).background(.purple.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
                    VStack(alignment: .leading, spacing: 4) {
                        Text(song.title).font(.headline)
                        Text(song.artist).foregroundStyle(.secondary)
                        Text([song.provider == "spotify" ? "Spotify" : "Apple Music", song.segmentDescription].compactMap { $0 }.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button {
                        Task { await app.detection.playMemorySong(provider: song.provider, providerID: song.providerID, playbackURL: song.playbackURL, title: song.title, artist: song.artist, startSeconds: song.startSeconds, endSeconds: song.endSeconds) }
                    } label: { Label(song.segmentDescription == nil ? "Listen" : "Play segment", systemImage: "play.fill") }
                    if let url = song.playbackURL, ["https", "spotify", "music"].contains(url.scheme ?? "") {
                        Link(destination: url) { Image(systemName: "arrow.up.right.square") }.help("Open in music provider")
                    }
                }.padding(16).background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 16))
            }
            if let error = app.detection.errorMessage { Label(error, systemImage: "info.circle").font(.callout).foregroundStyle(.secondary) }
            Divider()
            HStack { Text("Tags that mean something to you").font(.headline); Spacer(); Button("Edit tags") { tagsText = memory.tags.joined(separator: ", "); editingTags = true }.accessibilityIdentifier("memory.editTags") }
            Text(memory.tags.isEmpty ? "No tags yet. Add a feeling, a person, or your own name for this moment." : memory.tags.map { "#\($0)" }.joined(separator: "   ")).foregroundStyle(.secondary)
            if memory.classification.status != "complete" { Text("Automatic tags aren’t connected yet. Your own tags are saved to your profile.").font(.caption).foregroundStyle(.secondary) }
        }.frame(maxWidth: .infinity, alignment: .leading).accessibilityElement(children: .contain).accessibilityIdentifier("memory.detail")
            .sheet(isPresented: $editingTags) {
                VStack(alignment: .leading, spacing: 18) {
                    Text("Make these tags yours").font(.title2.weight(.semibold))
                    Text("Add tags or remove any suggestions. Separate tags with commas; they’ll be available for your next memory.").foregroundStyle(.secondary)
                    TextField("Tags", text: $tagsText).textFieldStyle(.roundedBorder).accessibilityIdentifier("memory.tagEditor")
                    if let error { Text(error).foregroundStyle(.red) }
                    HStack {
                        Button("Cancel") { editingTags = false }.disabled(saving)
                        Spacer()
                        Button("Save tags") {
                            saving = true
                            Task {
                                defer { saving = false }
                                do { try await store.updateTags(tagsText.components(separatedBy: ","), for: memory); editingTags = false }
                                catch { self.error = error.localizedDescription }
                            }
                        }.buttonStyle(.borderedProminent).disabled(saving).accessibilityIdentifier("memory.saveTags")
                    }
                }.padding(28).frame(width: 490)
                    .disabled(app.lock.isLocked)
                    .accessibilityHidden(app.lock.isLocked)
                    .overlay { if app.lock.isLocked { LockedView() } }
            }
    }
}

struct MemoryMediaView: View {
    @Environment(AppModel.self) private var app
    @Environment(MemoryStore.self) private var store
    let media: MemoryMedia
    let compact: Bool
    @State private var image: NSImage?
    @State private var player: AVPlayer?
    @State private var error: String?
    var body: some View {
        ZStack {
            Rectangle().fill(.quaternary.opacity(0.4))
            if let image { Image(nsImage: image).resizable().aspectRatio(contentMode: compact ? .fill : .fit) }
            else if let player { VideoPlayer(player: player).disabled(compact) }
            else if let error { VStack { Image(systemName: "photo.badge.exclamationmark"); Text(error).font(.caption).multilineTextAlignment(.center) }.padding() }
            else { ProgressView() }
            if compact && media.kind == "video" { Image(systemName: "play.circle.fill").font(.largeTitle).foregroundStyle(.white) }
        }
        .task(id: media.id) {
            do {
                let url = try await store.localMediaURL(media)
                try Task.checkCancellation()
                if media.kind == "video" { player = AVPlayer(url: url) }
                else {
                    image = NSImage(contentsOf: url)
                    if image == nil { error = "This photo could not be opened." }
                }
            } catch is CancellationError { } catch { self.error = "Attachment unavailable. Try refreshing." }
        }
        .onChange(of: app.lock.isLocked) { _, locked in if locked { player?.pause() } }
        .onDisappear { player?.pause(); player = nil }
    }
}
