import SwiftUI
import Photos

struct MemoryComposerView: View {
    var onSaved: (UUID) -> Void = { _ in }
    var onClose: () -> Void = { }
    @Environment(AppModel.self) private var app
    @Environment(MemoryStore.self) private var store
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var draft = MemoryDraft()
    @State private var moment = MemoryMomentSelection()
    @State private var library = MemoryPhotoLibrary()
    @State private var artwork = JourneyArtworkCache()
    @State private var picked: [String] = []
    @State private var showSelectedPhotos = false
    @State private var selectedAssets: [String: PHAsset] = [:]
    @State private var attachments: [Attachment] = []
    @State private var uploadingIDs = Set<String>()
    @State private var uploadTask: Task<Void, Never>?
    @State private var leadThumbnail: NSImage?
    @State private var leadColor: Color?
    @State private var order: [Step]
    @State private var step: Step
    @State private var furthest = 0
    @State private var detail: String?
    @State private var working = false
    @State private var reviewed = false
    @State private var classification: MemoryClassification?
    @State private var error: String?
    @State private var confirmDiscard = false
    @State private var didSave = false
    @State private var savedID: UUID?
    @State private var showCalendar = false
    @State private var operation: Task<Void, Never>?
    @State private var isActive = true
    @State private var durations: [UUID: Double] = [:]
    @State private var query = ""
    @State private var results: [CatalogSearchResult] = []
    @State private var searching = false
    @State private var searchError: String?
    @State private var searchTask: Task<Void, Never>?
    @State private var promptIndex = 0
    @State private var celebrate = false
    private let catalog = CatalogClient()

    /// Starting with the song when something is already playing puts the music-first hook up front.
    init(startWithSong: Bool = false, onSaved: @escaping (UUID) -> Void = { _ in }, onClose: @escaping () -> Void = { }) {
        self.onSaved = onSaved; self.onClose = onClose
        let order: [Step] = startWithSong ? [.song, .photo, .story, .review] : [.photo, .song, .story, .review]
        _order = State(initialValue: order); _step = State(initialValue: order[0])
    }

    private enum Step: Int, CaseIterable { case photo, song, story, review, complete }
    private struct Attachment: Identifiable {
        var media: MemoryMedia
        var metadata: MemoryCaptureMetadata
        var thumbnail: NSImage?
        var place: String?
        var assetID: String?
        var id: UUID { media.id }
    }

    // MARK: Derived state

    private var stepIndex: Int { order.firstIndex(of: step) ?? order.count }
    private var pendingAssets: [PHAsset] { picked.filter { id in !attachments.contains { $0.assetID == id } }.compactMap { selectedAssets[$0] } }
    /// Pending picks contribute PhotoKit dates/places immediately so the journey never waits on uploads.
    private var metadata: [MemoryCaptureMetadata] {
        attachments.map(\.metadata) + pendingAssets.map { MemoryCaptureMetadata(date: $0.creationDate, latitude: $0.location?.coordinate.latitude, longitude: $0.location?.coordinate.longitude) }
    }
    private var date: Date { moment.date(from: metadata) }
    private var inferredPlace: String? { attachments.compactMap(\.place).first }
    private var leadImage: NSImage? { leadThumbnail ?? attachments.first?.thumbnail }
    private var mediaCount: Int { attachments.count + pendingAssets.count }
    private var suggestedTags: [String] { MemoryDraft.normalizedTags(draft.tags + store.reusableTags + MemoryDraft.storyTags(draft.text) + ["Nostalgia", "Joy", "Road trip", "Together", "Slow days", "Celebration"]) }
    private var knownPeople: [String] { MemoryDraft.normalizedTags(store.memories.flatMap(\.people)) }
    private var recentSongs: [MemorySong] {
        var seen = Set<String>()
        return store.memories.flatMap(\.songs).filter { seen.insert("\($0.provider)|\($0.providerID ?? $0.title + $0.artist)").inserted && !hasSong($0) }
    }
    private var currentSong: MemorySong? { app.detection.track.map(MemorySong.init(track:)) }
    private var featuredSong: MemorySong? { draft.songs.first ?? (step == .song ? currentSong : nil) }
    private var featuredArtwork: NSImage? { featuredSong?.artworkURL.flatMap { artwork.images[$0] } }
    private var accent: Color {
        if let url = featuredSong?.artworkURL, let color = artwork.colors[url] { return color }
        return leadColor ?? .orange
    }
    private func isPlaying(_ song: MemorySong?) -> Bool {
        guard let song, app.detection.isPlaying, let track = app.detection.track else { return false }
        return track.title.caseInsensitiveCompare(song.title) == .orderedSame && track.artist.caseInsensitiveCompare(song.artist) == .orderedSame
    }

    private func title(for step: Step) -> String {
        switch step {
        case .photo: order.first == .song && !draft.songs.isEmpty ? "Now, where does it take you?" : "Find a little time machine."
        case .song: order.first == .song && currentSong != nil && draft.songs.isEmpty ? "Is this the one?" : "What was the soundtrack?"
        case .story: storyQuestions[promptIndex % storyQuestions.count]
        case .review: "A moment, made yours."
        case .complete: "Tucked into your soundtrack."
        }
    }
    private func subtitle(for step: Step) -> String {
        switch step {
        case .photo: "Choose the pictures that go with it."
        case .song: order.first == .song && currentSong != nil && draft.songs.isEmpty ? "It’s playing right now. Or find any song that takes you back." : "One song can bring it all back."
        case .story: storyContext.isEmpty ? "A few words, if you feel like it." : storyContext
        case .review: "Click anything on the card to change it."
        case .complete: "It’s waiting in your memories, whenever you want to return."
        }
    }

    // MARK: Layout

    var body: some View {
        VStack(spacing: 0) {
            navigation
            GeometryReader { geometry in
                VStack(spacing: 18) {
                    VStack(spacing: 8) {
                        Text(detail == nil ? title(for: step) : detailTitle).font(.system(size: geometry.size.height < 450 ? 29 : 36, weight: .semibold, design: .rounded))
                            .contentTransition(.opacity).id("title.\(promptIndex).\(detail ?? String(step.rawValue))")
                        Text(detail == nil ? subtitle(for: step) : "Only the details you want to keep.").font(.body).foregroundStyle(.secondary)
                    }.multilineTextAlignment(.center).padding(.top, 12)
                    ZStack {
                        Group {
                            if let detail { detailPage(detail) }
                            else {
                                switch step {
                                case .photo: photoPage
                                case .song: songPage
                                case .story: storyPage
                                case .review: reviewPage
                                case .complete: completionPage
                                }
                            }
                        }
                        .id(detail ?? String(step.rawValue))
                        .transition(.asymmetric(insertion: .opacity.combined(with: .offset(y: reduceMotion ? 0 : 18)), removal: .opacity))
                    }.frame(maxWidth: .infinity, maxHeight: .infinity)
                    if let error { Text(error).font(.callout).foregroundStyle(.red).accessibilityIdentifier("memory.error") }
                }.padding(.horizontal, 36).padding(.bottom, 12).frame(maxWidth: 1040).frame(maxWidth: .infinity)
            }
            footer
        }
        .background(Color(nsColor: .windowBackgroundColor).opacity(0.85))
        .overlay(alignment: .topTrailing) { Circle().fill(accent.opacity(0.1)).frame(width: 450).blur(radius: 85).offset(x: 230, y: -240).allowsHitTesting(false) }
        .environment(\.journeyAccent, accent)
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.6), value: accent)
        .accessibilityElement(children: .contain).accessibilityIdentifier("memory.journey")
        .disabled(app.lock.isLocked).accessibilityHidden(app.lock.isLocked)
        .overlay { if app.lock.isLocked { LockedView() } }
        .task { await library.open() }
        .task(id: library.status) { await library.loadYears() }
        .task(id: app.detection.track?.artworkURL) { artwork.load(app.detection.track?.artworkURL) }
        .onDisappear {
            isActive = false; operation?.cancel(); uploadTask?.cancel(); searchTask?.cancel()
            if !didSave { let media = attachments.map(\.media); Task { await store.discardMedia(media) } }
        }
        .dropDestination(for: URL.self) { urls, _ in
            guard step == .photo, !working, !app.lock.isLocked else { return false }
            let files = urls.filter(\.isFileURL)
            guard !files.isEmpty else { return false }; upload(files); return true
        }
    }

    private var navigation: some View {
        HStack {
            Button { goBack() } label: { Image(systemName: "arrow.left").frame(width: 36, height: 36) }
                .buttonStyle(.plain).disabled(working).keyboardShortcut(.cancelAction)
                .accessibilityLabel("Back").accessibilityIdentifier("memory.back").help("Back (Esc)")
            Spacer()
            if step != .complete { progressDots }
            Spacer()
            Button {
                if draft.canSave || !picked.isEmpty { confirmDiscard = true } else { onClose() }
            } label: { Image(systemName: "xmark").frame(width: 36, height: 36) }.buttonStyle(.plain).disabled(working || step == .complete).accessibilityLabel("Close memory").accessibilityIdentifier("memory.close")
        }.padding(.horizontal, 24).padding(.top, 8)
        .overlay {
            if confirmDiscard {
                HStack { Text("Keep this moment going?"); Button("Keep going") { confirmDiscard = false }; Button("Leave draft", role: .destructive) { onClose() } }
                    .padding(12).background(.regularMaterial, in: Capsule())
            }
        }
    }

    /// Completed and current steps are clickable; later steps unlock as they are reached.
    private var progressDots: some View {
        HStack(spacing: 8) {
            ForEach(Array(order.enumerated()), id: \.offset) { index, target in
                Button { jump(to: target) } label: {
                    Capsule().fill(index <= stepIndex ? accent : Color.primary.opacity(index <= furthest ? 0.25 : 0.1))
                        .frame(width: index == stepIndex ? 30 : 8, height: 6).padding(.vertical, 8).contentShape(Rectangle())
                }.buttonStyle(.plain).disabled(working || index > furthest || (index == stepIndex && detail == nil))
                    .help(["Photos", "Song", "Story", "Preview"][target.rawValue])
                    .accessibilityLabel("Go to \(["photos", "song", "story", "preview"][target.rawValue])")
            }
        }.animation(reduceMotion ? nil : .snappy, value: stepIndex)
            .accessibilityElement(children: .contain).accessibilityLabel("Step \(stepIndex + 1) of \(order.count)")
    }

    // MARK: Photo step

    private var photoPage: some View {
        VStack(spacing: 10) {
            Group {
                if library.status == .authorized || library.status == .limited { photoGallery }
                else { photoPermission }
            }.disabled(working)
            if attachments.contains(where: { $0.assetID == nil }) { droppedFiles }
        }
    }

    private var photoGallery: some View {
        VStack(spacing: 12) {
            HStack(spacing: 12) {
                yearStrip
                Button(showSelectedPhotos ? "Show all photos" : "\(picked.count) selected") { showSelectedPhotos.toggle() }
                    .buttonStyle(.plain).font(.caption).foregroundStyle(.secondary).disabled(picked.isEmpty && !showSelectedPhotos).fixedSize()
            }
            ScrollView {
                if library.assets.isEmpty { Text("No photos from this year.").foregroundStyle(.secondary).padding(40) }
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 12)], spacing: 12) {
                    ForEach(showSelectedPhotos ? picked.compactMap { selectedAssets[$0] } : library.assets, id: \.localIdentifier) { asset in
                        MemoryPhotoTile(asset: asset, selected: picked.contains(asset.localIdentifier)) { togglePhoto(asset.localIdentifier) }
                    }
                }.padding(4)
                if library.canLoadMore && !showSelectedPhotos { Button("Further back") { Task { await library.more() } }.buttonStyle(.plain).padding(15) }
            }.accessibilityIdentifier("memory.photoGrid")
            Text("Only photos you choose are uploaded to your memory.").font(.caption).foregroundStyle(.secondary)
        }
    }

    /// Only years that actually hold photos, as a scrubbable strip rather than an 80-item menu.
    private var yearStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                yearChip("All years", selected: library.year == nil && !showSelectedPhotos) { showSelectedPhotos = false; Task { await library.chooseYear(nil) } }
                ForEach(library.years, id: \.self) { year in
                    yearChip(String(year), selected: library.year == year && !showSelectedPhotos) { showSelectedPhotos = false; Task { await library.chooseYear(year) } }
                }
            }.padding(.vertical, 2)
        }.accessibilityIdentifier("memory.years")
    }
    private func yearChip(_ label: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label).font(.system(size: 13, weight: selected ? .semibold : .regular, design: .rounded)).monospacedDigit()
                .padding(.horizontal, 12).padding(.vertical, 6)
                .background(selected ? accent.opacity(0.2) : Color.primary.opacity(0.05), in: Capsule())
        }.buttonStyle(.plain).accessibilityAddTraits(selected ? .isSelected : [])
    }

    private var photoPermission: some View {
        VStack(spacing: 12) {
            MemoryJourneyIllustration(kind: .photo, image: leadImage).frame(maxHeight: 245)
            if mediaCount > 0 { Text("\(mediaCount) little windows back").font(.headline) }
            if library.isLoading { ProgressView() }
            else if library.status == .notDetermined {
                Button("Show my photos") { Task { await library.open(requestPermission: true) } }
                    .buttonStyle(JourneyButtonStyle()).accessibilityIdentifier("memory.photos")
                Text("Allow Photos once to choose pictures right here.\nOnly your selections are uploaded.").font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
            } else if library.status == .denied || library.status == .restricted {
                Text("Photos access is off. Drop a photo here from Photos,\nor keep going without one.").foregroundStyle(.secondary).multilineTextAlignment(.center)
            } else { Text("No photos here yet. You can keep going without one.").foregroundStyle(.secondary) }
        }.frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var droppedFiles: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack {
                ForEach(attachments.filter { $0.assetID == nil }) { item in
                    ZStack(alignment: .topTrailing) {
                        if let image = item.thumbnail { Image(nsImage: image).resizable().scaledToFill().frame(width: 65, height: 65).clipped().clipShape(RoundedRectangle(cornerRadius: 10)) }
                        Button { remove(item) } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(.white, .black.opacity(0.6)) }.buttonStyle(.plain).help("Remove attachment").disabled(working)
                    }
                }
            }
        }.frame(height: 70)
    }

    // MARK: Song step

    private var songPage: some View {
        HStack(spacing: 30) {
            MemoryJourneyIllustration(kind: .song, image: leadImage, artwork: featuredArtwork, spinning: isPlaying(featuredSong)).frame(maxWidth: 300)
            ScrollView { soundtrack.padding(.vertical, 4) }.scrollIndicators(.automatic).frame(maxWidth: 520)
        }.frame(maxWidth: 850).accessibilityElement(children: .contain).accessibilityIdentifier("memory.songStep")
    }

    private var soundtrack: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let song = currentSong, !hasSong(song) { playingNowCard(song) }
            ForEach($draft.songs) { $song in songRow($song) }
            songSearch
            if !recentSongs.isEmpty && query.isEmpty {
                Text("BRING BACK A SONG").font(.caption.weight(.semibold)).tracking(1).foregroundStyle(.secondary)
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack { ForEach(recentSongs.prefix(12)) { song in Button { var copy = song; copy.id = UUID(); add(copy) } label: { Label(song.title, systemImage: "plus") }.buttonStyle(.bordered).disabled(draft.songs.count >= 20) } }
                }
            }
        }.disabled(working)
    }

    private func playingNowCard(_ song: MemorySong) -> some View {
        Button { add(song, duration: app.detection.track?.trackDuration ?? (app.detection.playbackDuration > 0 ? app.detection.playbackDuration : nil)) } label: {
            HStack(spacing: 14) {
                artworkThumb(song.artworkURL, size: 52)
                VStack(alignment: .leading, spacing: 3) {
                    Text("PLAYING NOW").font(.caption2.weight(.bold)).tracking(1.5).foregroundStyle(accent)
                    Text(song.title).font(.headline).lineLimit(1); Text(song.artist).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                Label(draft.songs.isEmpty && order.first == .song ? "Yes, this one" : "Add", systemImage: "plus.circle.fill").font(.callout.weight(.semibold))
            }.padding(16).background(accent.opacity(0.12), in: RoundedRectangle(cornerRadius: 18)).contentShape(RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain).disabled(draft.songs.count >= 20).accessibilityIdentifier("memory.addCurrentSong")
    }

    private func songRow(_ song: Binding<MemorySong>) -> some View {
        let value = song.wrappedValue
        let duration = durations[value.id] ?? max(300, (value.endSeconds ?? 0) + 60)
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                artworkThumb(value.artworkURL, size: 46)
                VStack(alignment: .leading) { Text(value.title).font(.headline).lineLimit(1); Text(value.artist).foregroundStyle(.secondary).lineLimit(1) }
                Spacer()
                Button(value.startSeconds == nil ? "Keep a snippet" : "Whole song") {
                    if value.startSeconds == nil {
                        let start = isPlaying(value) ? min(app.detection.playbackPosition.rounded(), max(0, duration - 30)) : 0
                        song.wrappedValue.startSeconds = start; song.wrappedValue.endSeconds = min(duration, start + 30)
                    } else { song.wrappedValue.startSeconds = nil; song.wrappedValue.endSeconds = nil }
                    reviewed = false
                }.buttonStyle(.plain).foregroundStyle(accent)
                Button { draft.songs.removeAll { $0.id == value.id }; reviewed = false } label: { Image(systemName: "xmark.circle") }.buttonStyle(.plain).help("Remove song")
            }
            if let start = value.startSeconds {
                VStack(alignment: .leading, spacing: 6) {
                    SnippetRangeSlider(
                        start: Binding(get: { start }, set: { song.wrappedValue.startSeconds = $0; reviewed = false }),
                        end: Binding(get: { value.endSeconds ?? min(duration, start + 30) }, set: { song.wrappedValue.endSeconds = $0; reviewed = false }),
                        duration: duration, playhead: isPlaying(value) ? app.detection.playbackPosition : nil
                    ).accessibilityIdentifier("memory.snippet")
                    HStack {
                        Text("\(MemorySong.timestamp(start)) – \(MemorySong.timestamp(value.endSeconds ?? start + 30))").monospacedDigit()
                        if durations[value.id] == nil { Text("· song length unknown").foregroundStyle(.tertiary) }
                        Spacer()
                        if isPlaying(value) {
                            Button("Start here") {
                                let now = app.detection.playbackPosition.rounded()
                                song.wrappedValue.startSeconds = min(now, duration - 5); song.wrappedValue.endSeconds = min(duration, now + 30); reviewed = false
                            }.help("Start the snippet where the song is playing now")
                        }
                        Button { hear(value) } label: { Label("Hear it", systemImage: "play.fill") }.disabled(app.detection.isPlaybackBusy)
                    }.font(.caption).buttonStyle(.plain).foregroundStyle(.secondary)
                }.padding(.leading, 58)
            }
        }.padding(16).background(.background.opacity(0.6), in: RoundedRectangle(cornerRadius: 18))
            .transition(.opacity.combined(with: .scale(scale: 0.96)))
    }

    /// Any song in Juke's catalog (Spotify-backed), not only what happens to be playing.
    private var songSearch: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField(draft.songs.isEmpty && currentSong == nil ? "Search for any song" : "Search for another song", text: $query)
                    .textFieldStyle(.plain).onSubmit { runSearch(debounce: false) }.accessibilityIdentifier("memory.songSearch")
                if searching { ProgressView().controlSize(.small) }
                else if !query.isEmpty { Button { query = ""; results = [] } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(.tertiary) }.buttonStyle(.plain).help("Clear search") }
            }.padding(12).background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 14))
                .onChange(of: query) { _, _ in runSearch(debounce: true) }
            if let searchError { Text(searchError).font(.caption).foregroundStyle(.secondary) }
            ForEach(results.prefix(8)) { result in
                let song = MemorySong(track: result.recognizedTrack)
                Button { add(song, duration: result.durationMs.map { Double($0) / 1_000 }); query = ""; results = [] } label: {
                    HStack(spacing: 12) {
                        artworkThumb(result.resolvedArtworkURL, size: 40)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(result.name).lineLimit(1)
                            Text([result.artistNames, result.durationMs.map { MemorySong.timestamp(Double($0) / 1_000) }].compactMap { $0 }.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        }
                        Spacer()
                        Image(systemName: hasSong(song) ? "checkmark" : "plus.circle").foregroundStyle(accent)
                    }.padding(.horizontal, 10).padding(.vertical, 6).contentShape(Rectangle())
                }.buttonStyle(.plain).disabled(hasSong(song) || draft.songs.count >= 20)
                    .accessibilityIdentifier("memory.songResult.\(result.pk)")
            }
        }
    }

    private func artworkThumb(_ url: URL?, size: CGFloat) -> some View {
        AsyncImage(url: url) { image in image.resizable().scaledToFill() } placeholder: {
            ZStack { accent.opacity(0.18); Image(systemName: "music.note").foregroundStyle(accent) }
        }.frame(width: size, height: size).clipShape(RoundedRectangle(cornerRadius: size * 0.2)).accessibilityHidden(true)
    }

    // MARK: Story step

    private var storyQuestions: [String] {
        var questions: [String] = []
        let photoDated = metadata.contains { $0.date != nil } || moment.manualDate != nil
        if moment.usePhotoPlace, let place = inferredPlace { questions.append("What were you doing in \(place)?") }
        if let song = draft.songs.first { questions.append("Where were you when “\(song.title)” found you?") }
        if photoDated { questions.append("What do you remember about \(date.formatted(.dateTime.month(.wide).year()))?") }
        if mediaCount > 0 { questions.append("Who was there with you?") }
        questions += [store.insights.question, "What comes back to you?"]
        var seen = Set<String>()
        return questions.filter { seen.insert($0).inserted }
    }
    private var storyContext: String {
        var parts: [String] = []
        if metadata.contains(where: { $0.date != nil }) || moment.manualDate != nil { parts.append(date.formatted(.dateTime.month(.wide).year())) }
        if moment.usePhotoPlace, let place = inferredPlace { parts.append(place) }
        if let song = draft.songs.first { parts.append("“\(song.title)”") }
        return parts.joined(separator: " · ")
    }

    private var storyPage: some View {
        HStack(spacing: 35) {
            MemoryJourneyIllustration(kind: .story, image: leadImage, artwork: featuredArtwork, spinning: isPlaying(featuredSong)).frame(maxWidth: 290)
            VStack(alignment: .leading, spacing: 12) {
                ZStack(alignment: .topLeading) {
                    if draft.text.isEmpty { Text("I remember…").font(.system(size: 23, design: .serif)).foregroundStyle(.tertiary).padding(15).allowsHitTesting(false) }
                    TextEditor(text: $draft.text).font(.system(size: 23, design: .serif)).scrollContentBackground(.hidden).padding(10).accessibilityLabel("Memory description").accessibilityIdentifier("memory.body")
                }.frame(height: 185).background(.background.opacity(0.65), in: RoundedRectangle(cornerRadius: 22))
                storyTagChips
                HStack {
                    Text("No perfect words needed. Type #anything to tag it.").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    if storyQuestions.count > 1 {
                        Button { withAnimation(reduceMotion ? nil : .snappy) { promptIndex += 1 } } label: { Label("Ask me something else", systemImage: "shuffle") }
                            .buttonStyle(.plain).font(.caption).foregroundStyle(accent).accessibilityIdentifier("memory.nextQuestion")
                    }
                }
            }.frame(maxWidth: 470)
        }.frame(maxWidth: 850).disabled(working)
    }

    /// #tags typed into the story appear as chips the moment they're written.
    private var storyTagChips: some View {
        let tags = MemoryDraft.storyTags(draft.text)
        return HStack(spacing: 6) {
            ForEach(tags, id: \.self) { tag in
                Text("#" + tag).font(.caption.weight(.medium)).padding(.horizontal, 10).padding(.vertical, 5)
                    .background(accent.opacity(0.16), in: Capsule()).transition(.scale(scale: 0.6).combined(with: .opacity))
            }
        }.frame(height: tags.isEmpty ? 0 : 24, alignment: .leading)
            .animation(reduceMotion ? nil : .spring(response: 0.3, dampingFraction: 0.6), value: tags)
            .accessibilityElement(children: .combine).accessibilityLabel(tags.isEmpty ? "" : "Tags: " + tags.joined(separator: ", "))
    }

    // MARK: Preview & completion

    private var reviewPage: some View {
        HStack { Spacer(minLength: 0); memoryCard(interactive: true); Spacer(minLength: 0) }
            .accessibilityElement(children: .contain).accessibilityIdentifier("memory.preview")
    }

    /// The preview is the memory itself: every detail on the card is its own edit control.
    private func memoryCard(interactive: Bool) -> some View {
        HStack(alignment: .top, spacing: 24) {
            ZStack(alignment: .bottomTrailing) {
                VStack(spacing: 0) {
                    Group {
                        if let leadImage { Image(nsImage: leadImage).resizable().scaledToFill() }
                        else { LinearGradient(colors: [accent.opacity(0.55), .pink.opacity(0.25), .purple.opacity(0.3)], startPoint: .topLeading, endPoint: .bottomTrailing) }
                    }.frame(width: 210, height: 200).clipped().clipShape(RoundedRectangle(cornerRadius: 5))
                    HStack { Spacer(); if mediaCount > 1 { Text("+\(mediaCount - 1)").font(.caption2.weight(.semibold)).foregroundStyle(.black.opacity(0.45)) } }.frame(height: 22)
                }.padding(10).background(.white, in: RoundedRectangle(cornerRadius: 10))
                    .shadow(color: .black.opacity(0.12), radius: 12, y: 6).rotationEffect(.degrees(-3))
                if featuredSong != nil {
                    SpinningRecord(artwork: featuredArtwork, spinning: isPlaying(featuredSong)).frame(width: 96, height: 96).offset(x: 38, y: 26)
                }
            }.padding(.trailing, 30)
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 6) {
                    cardChip(date.formatted(date: .long, time: .omitted), systemImage: "calendar", enabled: interactive) { showCalendar = true; detail = "moment" }
                        .accessibilityIdentifier("memory.timeTravel")
                    if moment.usePhotoPlace, let place = inferredPlace { cardChip(place, systemImage: "mappin", enabled: interactive) { detail = "moment" } }
                }
                Text(draft.songs.first?.title ?? "A little piece of your life").font(.system(size: 26, weight: .semibold, design: .rounded)).lineLimit(2)
                if let song = draft.songs.first {
                    Text([song.artist, draft.songs.count > 1 ? "+\(draft.songs.count - 1) more" : nil, song.segmentDescription].compactMap { $0 }.joined(separator: " · ")).foregroundStyle(.secondary)
                }
                if !draft.text.isEmpty { Text(draft.text).font(.system(size: 17, design: .serif)).lineLimit(5).foregroundStyle(.primary.opacity(0.8)) }
                FlowLayout(spacing: 6) {
                    ForEach(draft.tags.prefix(6), id: \.self) { tag in cardChip("#" + tag, systemImage: nil, enabled: interactive) { detail = "tags" } }
                    cardChip(draft.tags.isEmpty ? "Add a feeling" : "Feelings", systemImage: "plus", enabled: interactive) { detail = "tags" }.accessibilityIdentifier("memory.tags")
                    if !knownPeople.isEmpty {
                        cardChip(draft.people.isEmpty ? "Who was there?" : draft.people.joined(separator: ", "), systemImage: "person.2", enabled: interactive) { detail = "people" }
                    }
                }.opacity(interactive ? 1 : 0.85)
            }.frame(maxWidth: 360, alignment: .leading)
        }.padding(26)
            .background(.background.opacity(0.8), in: RoundedRectangle(cornerRadius: 26))
            .overlay(RoundedRectangle(cornerRadius: 26).stroke(accent.opacity(0.25)))
            .shadow(color: .black.opacity(0.06), radius: 20, y: 10)
            .rotationEffect(.degrees(reduceMotion ? 0 : -0.8))
    }

    private func cardChip(_ label: String, systemImage: String?, enabled: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 4) {
                if let systemImage { Image(systemName: systemImage).font(.caption2) }
                Text(label).lineLimit(1)
            }.font(.caption.weight(.medium)).padding(.horizontal, 10).padding(.vertical, 6)
                .background(accent.opacity(0.13), in: Capsule())
        }.buttonStyle(.plain).allowsHitTesting(enabled).help(enabled ? "Change" : "")
    }

    /// The card tucks itself into a little stack of memories while the song plays, then opens on its own.
    private var completionPage: some View {
        ZStack {
            ForEach(0..<3) { index in
                RoundedRectangle(cornerRadius: 22).fill(.background.opacity(0.7)).overlay(RoundedRectangle(cornerRadius: 22).stroke(accent.opacity(0.2)))
                    .frame(width: 440, height: 250).rotationEffect(.degrees(Double(index - 1) * 5)).offset(y: 70 + Double(index) * 6)
                    .opacity(celebrate ? 1 : 0)
            }
            memoryCard(interactive: false)
                .scaleEffect(celebrate && !reduceMotion ? 0.62 : 1).offset(y: celebrate && !reduceMotion ? 40 : 0)
                .rotationEffect(.degrees(celebrate && !reduceMotion ? 2 : 0))
            ForEach(0..<9) { index in
                Image(systemName: index.isMultiple(of: 3) ? "heart.fill" : "sparkle").font(.system(size: CGFloat(12 + index % 4 * 4)))
                    .foregroundStyle(index.isMultiple(of: 2) ? accent : .pink.opacity(0.7))
                    .offset(x: cos(Double(index) * 0.7 + 3.4) * 260, y: celebrate && !reduceMotion ? -150 - Double(index % 3) * 30 : 20)
                    .opacity(celebrate ? 0 : 1).opacity(reduceMotion ? 0 : 1)
            }
        }.frame(maxWidth: .infinity, maxHeight: .infinity).accessibilityIdentifier("memory.complete")
            .onAppear {
                withAnimation(reduceMotion ? nil : .spring(response: 0.9, dampingFraction: 0.75).delay(0.25)) { celebrate = true }
                Task {
                    try? await Task.sleep(for: .seconds(reduceMotion ? 3.5 : 2.6))
                    if isActive, step == .complete, let savedID { onSaved(savedID) }
                }
            }
    }

    // MARK: Detail pages

    private var detailTitle: String { detail == "tags" ? "Keep a little of the feeling." : detail == "people" ? "Who made it yours?" : "A little time travel." }
    @ViewBuilder private func detailPage(_ value: String) -> some View {
        ScrollView { Group { switch value { case "tags": feelingChips; case "people": peopleChips; default: momentChips } }.padding(20) }.frame(maxWidth: 720)
    }

    private var momentChips: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Label(date.formatted(date: .abbreviated, time: .omitted), systemImage: "sun.max")
                    .font(.headline).padding(.horizontal, 14).padding(.vertical, 10).background(accent.opacity(0.14), in: Capsule()).accessibilityIdentifier("memory.date")
                Text(moment.isPhotoDate(metadata) ? "from your photo" : moment.manualDate == nil ? "today, unless you say otherwise" : "your chosen day").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button(showCalendar ? "Done" : "Time travel") { showCalendar.toggle() }.buttonStyle(.plain).foregroundStyle(accent)
            }
            if showCalendar {
                HStack(alignment: .top, spacing: 24) {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("When does this take you back to?").font(.headline)
                        Button("Today") { moment.manualDate = Calendar.current.startOfDay(for: Date()); reviewed = false }
                        Button("Yesterday") { moment.manualDate = Calendar.current.date(byAdding: .day, value: -1, to: Calendar.current.startOfDay(for: Date())); reviewed = false }.accessibilityIdentifier("memory.yesterday")
                        if metadata.contains(where: { $0.date != nil }) { Button("Use the photo’s date") { moment.manualDate = nil; reviewed = false } }
                        Text("No need to remember the hour.").font(.caption).foregroundStyle(.secondary)
                    }.buttonStyle(.bordered)
                    Spacer()
                    MemoryDayPicker(selection: Binding(get: { date }, set: { moment.manualDate = $0; reviewed = false }))
                }.padding(20).background(.background.opacity(0.6), in: RoundedRectangle(cornerRadius: 20))
            }
            if let place = inferredPlace {
                Button {
                    moment.usePhotoPlace.toggle(); reviewed = false
                } label: { Label(moment.usePhotoPlace ? "\(place)  ×" : "Add \(place)", systemImage: "mappin.and.ellipse") }
                    .buttonStyle(.bordered).tint(moment.usePhotoPlace ? accent : .secondary)
                    .help("Place from your photo. Click to include or remove it.")
            }
        }.disabled(working)
    }

    private var peopleChips: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("A familiar face?").font(.headline)
            Text("People from your memories. Add anyone who was there.").font(.caption).foregroundStyle(.secondary)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 120))], alignment: .leading) {
                ForEach(knownPeople, id: \.self) { person in
                    Button { if draft.people.contains(person) { draft.people.removeAll { $0 == person } } else { draft.people.append(person) }; reviewed = false } label: { Label(person, systemImage: draft.people.contains(person) ? "checkmark" : "plus") }.buttonStyle(.bordered)
                }
            }
        }.disabled(working)
    }

    private var feelingChips: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Pick a little of the feeling.").font(.title2.weight(.semibold))
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 130))], spacing: 10) {
                ForEach(suggestedTags.prefix(40), id: \.self) { value in
                    let selected = draft.tags.contains { $0.caseInsensitiveCompare(value) == .orderedSame }
                    Button { toggleTag(value) } label: {
                        HStack { Text(value).lineLimit(1); Spacer(minLength: 3); Image(systemName: selected ? "checkmark" : "plus").font(.caption) }.padding(.horizontal, 12).padding(.vertical, 10)
                            .background(selected ? accent.opacity(0.2) : Color.primary.opacity(0.04), in: Capsule())
                            .overlay(Capsule().stroke(selected ? accent.opacity(0.45) : .clear))
                    }.buttonStyle(.plain).accessibilityIdentifier("memory.reuseTag.\(value)").accessibilityAddTraits(selected ? .isSelected : [])
                }
            }
            Text("Make your own with a #tag in your story. It’ll be here next time.").font(.caption).foregroundStyle(.secondary)
        }.disabled(working)
    }

    // MARK: Footer

    private var footer: some View {
        HStack {
            if working { ProgressView().controlSize(.small); Text(workingMessage).font(.caption).foregroundStyle(.secondary) }
            else if !uploadingIDs.isEmpty { ProgressView().controlSize(.small); Text("Bringing \(uploadingIDs.count) \(uploadingIDs.count == 1 ? "photo" : "photos") along in the background…").font(.caption).foregroundStyle(.secondary) }
            else { Text(step == .story && !draft.canSave ? "A few words make this a memory." : "Just for you.").font(.caption).foregroundStyle(.secondary) }
            Spacer()
            Button { advance() } label: {
                HStack(spacing: 12) {
                    Text(primaryTitle); Image(systemName: step == .review && detail == nil ? "heart" : "arrow.right")
                    Text(usesCommandReturn ? "⌘↩" : "↩").font(.caption.weight(.medium)).opacity(0.55)
                }.padding(.horizontal, 6)
            }
            .buttonStyle(JourneyButtonStyle()).disabled(working || (step == .story && !draft.canSave && detail == nil))
            .keyboardShortcut(usesCommandReturn ? KeyboardShortcut(.return, modifiers: .command) : .defaultAction)
            .accessibilityIdentifier(step == .review && detail == nil ? "memory.save" : step == .complete ? "memory.openSaved" : "memory.next")
        }.padding(.horizontal, 36).padding(.vertical, 20)
    }
    /// Text entry owns plain Return on the song (search) and story steps.
    private var usesCommandReturn: Bool { detail == nil && (step == .song || step == .story) }
    private var workingMessage: String {
        if !uploadingIDs.isEmpty { return "Tucking in your photos…" }
        return step == .photo ? "Bringing your photos along…" : "One little moment…"
    }
    private var primaryTitle: String {
        if detail != nil { return "Feels right" }
        switch step {
        case .photo: return picked.isEmpty && attachments.isEmpty ? "Continue without photos" : "Bring these along"
        case .song: return draft.songs.isEmpty ? "Continue without a song" : "Keep going"
        case .story: return "See your memory"
        case .review: return "Keep this memory"
        case .complete: return "Open my memory"
        }
    }

    // MARK: Navigation

    private func move(to target: Step) {
        withAnimation(reduceMotion ? nil : .spring(response: 0.48, dampingFraction: 0.88)) {
            detail = nil; step = target
            if let index = order.firstIndex(of: target) { furthest = max(furthest, index) }
        }
    }
    private func next(after current: Step) -> Step { order.firstIndex(of: current).flatMap { $0 + 1 < order.count ? order[$0 + 1] : nil } ?? .review }
    private func goBack() {
        if confirmDiscard { confirmDiscard = false; return }
        if detail != nil { withAnimation { detail = nil }; return }
        if step == .complete { if let savedID { onSaved(savedID) }; return }
        if stepIndex > 0 { leave(step, to: order[stepIndex - 1]) }
        else if draft.canSave || !picked.isEmpty { confirmDiscard = true }
        else { onClose() }
    }
    private func jump(to target: Step) {
        guard !working else { return }
        if target == .review && step != .review { leave(step, to: .story); reviewTags(); return }
        leave(step, to: target)
    }
    /// Leaving the photo step starts uploads in the background instead of blocking on them.
    private func leave(_ current: Step, to target: Step) {
        if current == .photo { importSelection() }
        move(to: target)
    }
    private func advance() {
        if detail != nil { withAnimation { detail = nil }; return }
        switch step {
        case .photo: leave(.photo, to: next(after: .photo))
        case .song: leave(.song, to: next(after: .song))
        case .story: reviewTags()
        case .review: save()
        case .complete: if let savedID { onSaved(savedID) }
        }
    }

    // MARK: Songs

    private func add(_ song: MemorySong, duration: Double? = nil) {
        guard !hasSong(song), draft.songs.count < 20 else { return }
        if let duration, duration > 0 { durations[song.id] = duration }
        artwork.load(song.artworkURL)
        withAnimation(reduceMotion ? nil : .snappy) { draft.songs.append(song) }
        reviewed = false
    }
    private func hear(_ song: MemorySong) {
        Task { await app.detection.playMemorySong(provider: song.provider, providerID: song.providerID, playbackURL: song.playbackURL, title: song.title, artist: song.artist, startSeconds: song.startSeconds, endSeconds: song.endSeconds) }
    }
    private func runSearch(debounce: Bool) {
        searchTask?.cancel()
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard text.count >= 2, let token = app.session?.accessToken else { results = []; searching = false; searchError = nil; return }
        searchTask = Task {
            if debounce { try? await Task.sleep(for: .milliseconds(350)) }
            guard !Task.isCancelled else { return }
            searching = true
            defer { if !Task.isCancelled { searching = false } }
            do {
                let found = try await catalog.search(text, kind: "tracks", token: token)
                guard !Task.isCancelled else { return }
                results = found; searchError = found.isEmpty ? "No songs found for “\(text)”." : nil
                for result in found.prefix(8) { artwork.load(result.resolvedArtworkURL) }
            } catch { if !Task.isCancelled { searchError = error.localizedDescription } }
        }
    }
    private func hasSong(_ song: MemorySong) -> Bool { draft.songs.contains { $0.provider == song.provider && $0.title == song.title && $0.artist == song.artist && $0.providerID == song.providerID } }

    // MARK: Photos

    private func togglePhoto(_ id: String) {
        if picked.contains(id) { selectedAssets[id] = nil; picked.removeAll { $0 == id }; if let item = attachments.first(where: { $0.assetID == id }) { remove(item) } }
        else if picked.count + attachments.filter({ $0.assetID == nil }).count < 12 { withAnimation(reduceMotion ? nil : .snappy) { picked.append(id); selectedAssets[id] = library.assets.first { $0.localIdentifier == id } } }
    }
    private func importSelection() {
        refreshLeadPhoto()
        // Snapshot ordered selection; already imported or in-flight assets are retained on Back.
        let assets = pendingAssets.filter { !uploadingIDs.contains($0.localIdentifier) }
        guard !assets.isEmpty else { return }
        uploadingIDs.formUnion(assets.map(\.localIdentifier))
        let previous = uploadTask
        uploadTask = Task {
            await previous?.value
            for asset in assets {
                defer { uploadingIDs.remove(asset.localIdentifier) }
                guard isActive, !Task.isCancelled else { return }
                guard picked.contains(asset.localIdentifier) else { continue }
                do { try await append(MemoryPhotoLibrary.file(for: asset), assetID: asset.localIdentifier) }
                catch is CancellationError { return }
                catch { self.error = error.localizedDescription }
            }
        }
    }
    private func refreshLeadPhoto() {
        guard let first = picked.first.flatMap({ selectedAssets[$0] }) else {
            if attachments.isEmpty { leadThumbnail = nil; leadColor = nil }
            return
        }
        Task {
            guard let image = await MemoryPhotoLibrary.thumbnail(for: first), isActive else { return }
            leadThumbnail = image
            leadColor = ArtworkPalette.averageColor(image).map(Color.journeyAccent(from:))
        }
    }
    private func remove(_ item: Attachment) {
        attachments.removeAll { $0.id == item.id }; draft.mediaIDs.removeAll { $0 == item.id }; reviewed = false
        Task { await store.discardMedia([item.media]) }
    }
    private func append(_ file: MemoryImportedFile, assetID: String? = nil) async throws {
        try Task.checkCancellation()
        let media = try await store.upload(file.data, filename: file.filename, contentType: file.contentType)
        guard isActive, !Task.isCancelled else { await store.discardMedia([media]); throw CancellationError() }
        // The photo may have been deselected while it was uploading.
        if let assetID, !picked.contains(assetID) { await store.discardMedia([media]); return }
        let details = MemoryCaptureMetadata.authorizedAsset(assetID)?.fillingMissing(from: file.metadata) ?? file.metadata
        attachments.append(Attachment(media: media, metadata: details, thumbnail: file.thumbnail.flatMap(NSImage.init(data:)), assetID: assetID))
        draft.mediaIDs.append(media.id); reviewed = false
        if leadThumbnail == nil, attachments.count == 1, let image = attachments.first?.thumbnail {
            leadColor = ArtworkPalette.averageColor(image).map(Color.journeyAccent(from:))
        }
        let place = await details.placeName()
        if let index = attachments.firstIndex(where: { $0.id == media.id }) { attachments[index].place = place }
    }
    private func upload(_ urls: [URL]) {
        guard !working else { return }
        working = true; error = nil
        operation = Task {
            defer { working = false }
            for url in urls.prefix(max(0, 12 - attachments.count)) {
                let access = url.startAccessingSecurityScopedResource()
                defer { if access { url.stopAccessingSecurityScopedResource() } }
                do { try await append(MemoryImportedFile.read(url)) }
                catch is CancellationError { break } catch { self.error = error.localizedDescription; break }
            }
        }
    }

    // MARK: Save

    private func toggleTag(_ value: String) {
        if draft.tags.contains(where: { $0.caseInsensitiveCompare(value) == .orderedSame }) {
            draft.tags.removeAll { $0.caseInsensitiveCompare(value) == .orderedSame }; draft.excludedTags = MemoryDraft.normalizedTags(draft.excludedTags + [value])
        } else {
            draft.tags = MemoryDraft.normalizedTags(draft.tags + [value]); draft.excludedTags.removeAll { $0.caseInsensitiveCompare(value) == .orderedSame }
        }
    }
    private func prepare() {
        draft.title = ""; draft.occurredAt = date
        draft.place = moment.usePhotoPlace ? inferredPlace ?? "" : ""
        draft.tags = MemoryDraft.normalizedTags(draft.tags + MemoryDraft.storyTags(draft.text).filter { tag in !draft.excludedTags.contains { $0.caseInsensitiveCompare(tag) == .orderedSame } })
    }
    /// Media-only memories need their uploads before validation; everything else can classify right away.
    private func reviewTags() {
        working = true; error = nil
        operation = Task {
            defer { working = false }
            if draft.songs.isEmpty && draft.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { await uploadTask?.value }
            guard isActive, !Task.isCancelled else { return }
            prepare()
            if let message = draft.validationMessage { error = message; return }
            do {
                let result = try await store.classify(draft)
                guard isActive, !Task.isCancelled else { return }
                classification = result
                draft.tags = MemoryDraft.normalizedTags(draft.tags + result.tags.filter { tag in !draft.excludedTags.contains { $0.caseInsensitiveCompare(tag) == .orderedSame } })
                reviewed = true; move(to: .review)
            } catch is CancellationError { } catch { self.error = error.localizedDescription }
        }
    }
    private func save() {
        working = true; error = nil
        operation = Task {
            defer { working = false }
            await uploadTask?.value
            guard isActive, !Task.isCancelled else { return }
            prepare()
            do {
                let saved = try await store.save(draft); didSave = true
                guard isActive else { return }
                savedID = saved.id; playSnippetOnSave(); move(to: .complete)
            }
            catch is CancellationError { } catch { self.error = error.localizedDescription }
        }
    }
    /// Only when Juke can control Spotify directly; never hands off to another app uninvited.
    private func playSnippetOnSave() {
        guard let song = draft.songs.first, song.provider == "spotify", song.providerID != nil, !isPlaying(song),
              app.detection.spotifyPlaybackAccess == .available, !app.detection.isSpotifySpectatorMode else { return }
        hear(song)
    }
}

/// Wraps chips onto new lines at the available width.
private struct FlowLayout: Layout {
    var spacing: CGFloat = 6
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = rows(for: proposal.width ?? .infinity, subviews: subviews)
        var width: CGFloat = 0, height: CGFloat = 0
        for row in rows {
            let rowWidth: CGFloat = row.reduce(0) { $0 + $1.width } + spacing * CGFloat(max(0, row.count - 1))
            let rowHeight: CGFloat = row.map(\.height).max() ?? 0
            width = max(width, rowWidth); height += rowHeight
        }
        height += spacing * CGFloat(max(0, rows.count - 1))
        return CGSize(width: width, height: height)
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY, index = 0
        for row in rows(for: bounds.width, subviews: subviews) {
            var x = bounds.minX
            for size in row {
                subviews[index].place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size)); x += size.width + spacing; index += 1
            }
            y += (row.map(\.height).max() ?? 0) + spacing
        }
    }
    private func rows(for width: CGFloat, subviews: Subviews) -> [[CGSize]] {
        var rows: [[CGSize]] = [[]], lineWidth: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if lineWidth + size.width > width, !(rows.last?.isEmpty ?? true) { rows.append([]); lineWidth = 0 }
            rows[rows.count - 1].append(size); lineWidth += size.width + spacing
        }
        return rows
    }
}

private struct MemoryDayPicker: View {
    @Binding var selection: Date
    @State private var month: Date = Date()
    private let calendar = Calendar.current
    private var start: Date { calendar.dateInterval(of: .month, for: month)!.start }
    private var offset: Int { (calendar.component(.weekday, from: start) - calendar.firstWeekday + 7) % 7 }
    @Environment(\.journeyAccent) private var accent
    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Button { move(-1) } label: { Image(systemName: "chevron.left") }.accessibilityLabel("Previous month")
                Spacer(); Text(month.formatted(.dateTime.month(.wide).year())).font(.headline); Spacer()
                Button { move(1) } label: { Image(systemName: "chevron.right") }.accessibilityLabel("Next month")
            }.buttonStyle(.plain)
            HStack { Button("A year earlier") { move(-12) }; Spacer(); Button("A year later") { move(12) } }.font(.caption).buttonStyle(.plain).foregroundStyle(.secondary)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 7), spacing: 5) {
                ForEach(0..<7, id: \.self) { index in Text(calendar.veryShortStandaloneWeekdaySymbols[(index + calendar.firstWeekday - 1) % 7]).font(.caption).foregroundStyle(.secondary) }
                ForEach(0..<(offset + (calendar.range(of: .day, in: .month, for: month)?.count ?? 30)), id: \.self) { index in
                    if index < offset { Color.clear.frame(height: 28) }
                    else {
                        let day = calendar.date(byAdding: .day, value: index - offset, to: start)!
                        Button { selection = day } label: { Text("\(index - offset + 1)").frame(maxWidth: .infinity).frame(height: 28).background(calendar.isDate(day, inSameDayAs: selection) ? accent.opacity(0.3) : .clear, in: Circle()) }
                            .buttonStyle(.plain).accessibilityLabel(day.formatted(date: .complete, time: .omitted))
                    }
                }
            }
        }.frame(width: 280).onAppear { month = selection }.onChange(of: selection) { _, date in month = date }
    }
    private func move(_ count: Int) { month = calendar.date(byAdding: .month, value: count, to: start) ?? month }
}
