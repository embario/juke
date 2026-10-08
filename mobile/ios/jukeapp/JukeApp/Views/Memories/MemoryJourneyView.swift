import PhotosUI
import SwiftUI

/// New memory, as a short journey (photos → song → story → preview → done), like the Mac.
/// Each step is one question on one screen; the dots show progress and go back to steps
/// already reached; nothing is lost when you step back.
struct MemoryJourneyView: View {
    var startWithSong = false
    var onClose: () -> Void
    @Environment(VibeAppModel.self) private var model
    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private struct Attachment: Identifiable { var media: MemoryMedia; var thumbnail: UIImage?; var id: UUID { media.id } }

    @State private var flow: MemoryJourneyFlow
    @State private var forward = true
    @State private var draft = MemoryDraft()
    @State private var dateChosenByHand = false
    @State private var people = ""
    @State private var picks: [PhotosPickerItem] = []
    @State private var attachments: [Attachment] = []
    @State private var uploading = false
    @State private var query = ""
    @State private var results: [CatalogSearchResult] = []
    @State private var searching = false
    @State private var saving = false
    @State private var gate = MemoryUploadGate()
    @State private var confirmDiscard = false
    @State private var didSave = false
    @State private var error: String?
    private let catalog = CatalogClient()

    init(startWithSong: Bool = false, onClose: @escaping () -> Void) {
        self.startWithSong = startWithSong
        self.onClose = onClose
        var initialFlow = MemoryJourneyFlow(startWithSong: startWithSong)
        var initialDraft = MemoryDraft()
        #if DEBUG
        if let value = ProcessInfo.processInfo.arguments.first(where: { $0.hasPrefix("--uitesting-memory-step=") })?.dropFirst(24) {
            // A step name (photo, song, story, review) or a count of steps to skip.
            let names: [String: MemoryJourneyFlow.Step] = ["photo": .photo, "song": .song, "story": .story, "review": .review]
            var steps = Int(value) ?? 0
            if let target = names[String(value)], let position = initialFlow.order.firstIndex(of: target) { steps = position }
            for _ in 0..<steps { initialFlow.next() }
            let reached = initialFlow.furthest
            if reached >= 2 || value == "review" || value == "story" {
                var song = MemorySong(title: "Blue in Green", artist: "Miles Davis", provider: "spotify", providerID: "0aWMVrwxPNYkKmFthzmpRi")
                song.artworkURL = nil
                initialDraft.songs = [song]
            }
            if value == "review" || value == "story" || reached >= 3 { initialDraft.text = "Driving home with the windows down. #summer #roadtrip"; initialDraft.place = "Highway 1" }
        }
        #endif
        _flow = State(initialValue: initialFlow)
        _draft = State(initialValue: initialDraft)
    }

    private var gentle: Animation? { reduceMotion ? nil : .smooth(duration: 0.45) }

    // MARK: Derived

    /// What is playing now: the radio's record, or whatever Apple Music / Spotify reports.
    private var currentSong: MemorySong? {
        if model.radio.isOnAir, let track = model.radio.track {
            var song = MemorySong(title: track.title, artist: track.artist, provider: "spotify", providerID: track.spotifyId,
                                  playbackURL: URL(string: "spotify:track:\(track.spotifyId)"))
            song.artworkURL = track.artworkURL
            return song
        }
        return model.nowPlaying.track.map { MemorySong(track: NowPlayingRecognitionFeed.recognized($0)) }
    }
    private var questions: [String] {
        MemoryJourneyFlow.questions(place: draft.place.isEmpty ? nil : draft.place, songTitle: draft.songs.first?.title,
                                    date: dateChosenByHand || !attachments.isEmpty ? draft.occurredAt : nil,
                                    hasMedia: !attachments.isEmpty, insightQuestion: model.memories.insights.question)
    }
    private var storyContext: String {
        var parts: [String] = []
        if dateChosenByHand || !attachments.isEmpty { parts.append(draft.occurredAt.formatted(.dateTime.month(.wide).year())) }
        if !draft.place.isEmpty { parts.append(draft.place) }
        if let song = draft.songs.first { parts.append("“\(song.title)”") }
        return parts.joined(separator: " · ")
    }

    // MARK: Body

    var body: some View {
        VStack(spacing: 0) {
            topBar
            VStack(spacing: 6) {
                Text(flow.title(draftHasSong: !draft.songs.isEmpty, nowPlaying: currentSong != nil,
                                question: MemoryJourneyFlow.question(at: flow.promptIndex, in: questions)))
                    .font(.title.bold()).foregroundStyle(theme.ink.color).id("t\(flow.step.rawValue)-\(flow.promptIndex)")
                    .transition(.opacity)
                Text(flow.subtitle(draftHasSong: !draft.songs.isEmpty, nowPlaying: currentSong != nil, storyContext: storyContext))
                    .font(.subheadline).foregroundStyle(theme.sub.color)
            }
            .multilineTextAlignment(.center).padding(.horizontal, 24).padding(.top, 8)
            ZStack {
                page.id(flow.step)
                    .transition(reduceMotion ? .opacity : .asymmetric(
                        insertion: .move(edge: forward ? .trailing : .leading).combined(with: .opacity),
                        removal: .move(edge: forward ? .leading : .trailing).combined(with: .opacity)))
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity).clipped()
            if let error { Label(error, systemImage: "exclamationmark.triangle.fill").font(.footnote).foregroundStyle(theme.ink.color).padding(.horizontal, 20) }
            footer
        }
        .background(VibeBackground(atmosphere: model.atmosphere))
        .animation(gentle, value: flow.step)
        .onChange(of: picks) { _, items in Task { await upload(items) } }
        .onDisappear { if !didSave { gate.abandon(); discard() } }
        .confirmationDialog("Keep this moment going?", isPresented: $confirmDiscard, titleVisibility: .visible) {
            Button("Keep going", role: .cancel) {}
            Button("Leave draft", role: .destructive) { discard(); onClose() }
        }
        .accessibilityIdentifier("memory.journey")
    }

    private var topBar: some View {
        HStack {
            Button { goBack() } label: { Image(systemName: "arrow.left").frame(width: 44, height: 44) }
                .disabled(saving || flow.step == .complete || (flow.isFirst && !flow.showsProgress))
                .opacity(flow.isFirst || flow.step == .complete ? 0 : 1)
                .accessibilityLabel("Back").accessibilityIdentifier("memory.back")
            Spacer()
            if flow.showsProgress {
                HStack(spacing: 8) {
                    ForEach(Array(flow.order.enumerated()), id: \.offset) { position, target in
                        Button { move(to: target) } label: {
                            Capsule().fill(position <= flow.index ? theme.accent.color : theme.line)
                                .frame(width: position == flow.index ? 30 : 8, height: 6).padding(.vertical, 18).contentShape(Rectangle())
                        }
                        .disabled(saving || position > flow.furthest)
                        .accessibilityLabel("Go to \(["photos", "song", "story", "preview"][target.rawValue])")
                    }
                }
                .accessibilityElement(children: .contain).accessibilityLabel("Step \(flow.index + 1) of \(flow.order.count)")
            }
            Spacer()
            Button { if draft.canSave || !attachments.isEmpty { confirmDiscard = true } else { onClose() } } label: { Image(systemName: "xmark").frame(width: 44, height: 44) }
                // Leaving mid-upload would strand the file on the server, so wait for it.
                .disabled(saving || uploading).opacity(flow.step == .complete ? 0 : 1)
                .accessibilityLabel("Close memory").accessibilityIdentifier("memory.close")
        }
        .foregroundStyle(theme.ink.color).padding(.horizontal, 12)
    }

    private var footer: some View {
        Button { Task { await advance() } } label: {
            Text(flow.primaryLabel(hasPhotos: !attachments.isEmpty, hasSong: !draft.songs.isEmpty)).frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent).controlSize(.large)
        .disabled(uploading || saving || (flow.step == .review && !MemoryJourneyFlow.canSave(draft, attachmentIDs: attachments.map(\.media.id))))
        .padding(.horizontal, 20).padding(.vertical, 12)
        .background(.bar)
        .accessibilityIdentifier("memory.next")
    }

    @ViewBuilder private var page: some View {
        switch flow.step {
        case .photo: photoPage
        case .song: songPage
        case .story: storyPage
        case .review: reviewPage
        case .complete: completePage
        }
    }

    // MARK: Photos

    private var photoPage: some View {
        ScrollView {
            VStack(spacing: 16) {
                PhotosPicker(selection: $picks, maxSelectionCount: 8, matching: .any(of: [.images, .videos])) {
                    VStack(spacing: 10) {
                        Image(systemName: uploading ? "arrow.up.circle" : "photo.badge.plus").font(.system(size: 40)).foregroundStyle(theme.accent.color)
                        Text(attachments.isEmpty ? "Add photos or videos" : "Add more").font(.headline).foregroundStyle(theme.ink.color)
                        if uploading { ProgressView() }
                    }
                    .frame(maxWidth: .infinity, minHeight: 150)
                    .background(theme.card.color, in: RoundedRectangle(cornerRadius: JukeRadius.card, style: .continuous))
                }
                .accessibilityIdentifier("memory.addPhotos")
                if !attachments.isEmpty {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: 3), spacing: 10) {
                        ForEach(attachments) { item in
                            ZStack(alignment: .topTrailing) {
                                Group {
                                    if let image = item.thumbnail { Image(uiImage: image).resizable().scaledToFill() }
                                    else { ZStack { theme.well.color; Image(systemName: item.media.kind == "video" ? "play.rectangle" : "photo").foregroundStyle(theme.sub.color) } }
                                }
                                .aspectRatio(1, contentMode: .fit).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                                Button { remove(item) } label: { Image(systemName: "xmark.circle.fill").symbolRenderingMode(.palette).foregroundStyle(.white, .black.opacity(0.55)).font(.title3) }
                                    .padding(4).accessibilityLabel("Remove this photo")
                            }
                        }
                    }
                }
            }
            .padding(.horizontal, 20).padding(.vertical, 8)
        }
    }

    // MARK: Song

    private var songPage: some View {
        VStack(spacing: 10) {
            if let song = draft.songs.first {
                songRow(song, trailing: AnyView(Button { draft.songs = [] } label: { Image(systemName: "xmark.circle.fill").font(.title3).foregroundStyle(theme.sub.color) }.accessibilityLabel("Remove the song")))
                    .padding(.horizontal, 20)
            } else if let song = currentSong {
                Button { draft.songs = [song] } label: {
                    songRow(song, trailing: AnyView(Text("Use this").font(.subheadline.weight(.semibold)).foregroundStyle(theme.accent.color)), caption: "Playing now")
                }
                .buttonStyle(.plain).padding(.horizontal, 20).accessibilityIdentifier("memory.useCurrentSong")
            }
            TextField("Search any song", text: $query).textFieldStyle(.roundedBorder).submitLabel(.search)
                .padding(.horizontal, 20).onSubmit { Task { await search() } }
                .accessibilityIdentifier("memory.songSearch")
            List {
                if searching { ProgressView().frame(maxWidth: .infinity).listRowBackground(Color.clear) }
                ForEach(results.prefix(12)) { result in
                    Button { draft.songs = [MemorySong(track: result.recognizedTrack)]; query = ""; results = [] } label: {
                        songRow(MemorySong(track: result.recognizedTrack), trailing: AnyView(Image(systemName: "plus.circle").font(.title3).foregroundStyle(theme.sub.color)))
                    }
                    .listRowBackground(Color.clear)
                }
            }
            .listStyle(.plain).scrollContentBackground(.hidden).scrollDismissesKeyboard(.interactively)
        }
    }

    private func songRow(_ song: MemorySong, trailing: AnyView, caption: String? = nil) -> some View {
        HStack(spacing: 12) {
            AsyncImage(url: song.artworkURL) { $0.resizable().scaledToFill() } placeholder: {
                ZStack { theme.well.color; Image(systemName: "music.note").foregroundStyle(theme.sub.color) }
            }
            .frame(width: 48, height: 48).clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                if let caption { Text(caption.uppercased()).font(.caption2.bold()).tracking(1).foregroundStyle(theme.accent.color) }
                Text(song.title).font(.body.weight(.semibold)).foregroundStyle(theme.ink.color).lineLimit(1)
                Text(song.artist).font(.caption).foregroundStyle(theme.sub.color).lineLimit(1)
            }
            Spacer(minLength: 0)
            trailing
        }
        .padding(10).background(theme.card.color, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    // MARK: Story

    private var storyPage: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                ZStack(alignment: .topLeading) {
                    if draft.text.isEmpty { Text("I remember…").font(.system(size: 22, design: .serif)).foregroundStyle(.tertiary).padding(16).allowsHitTesting(false) }
                    TextEditor(text: $draft.text).font(.system(size: 22, design: .serif)).scrollContentBackground(.hidden).padding(10)
                        .accessibilityLabel("Memory description").accessibilityIdentifier("memory.body")
                }
                .frame(minHeight: 200).background(theme.well.color, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                let tags = MemoryDraft.storyTags(draft.text)
                if !tags.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) { ForEach(tags, id: \.self) { tag in chip("#" + tag) } }
                    }
                }
                HStack {
                    Text("No perfect words needed. Type #anything to tag it.").font(.footnote).foregroundStyle(theme.sub.color)
                    Spacer()
                    if questions.count > 1 {
                        Button { withAnimation(gentle) { flow.promptIndex += 1 } } label: { Label("Ask me something else", systemImage: "shuffle").font(.footnote) }
                            .accessibilityIdentifier("memory.nextQuestion")
                    }
                }
            }
            .padding(.horizontal, 20).padding(.vertical, 8)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private func chip(_ text: String) -> some View {
        Text(text).font(.caption.weight(.medium)).foregroundStyle(theme.ink.color)
            .padding(.horizontal, 10).padding(.vertical, 5).background(theme.accentSoft.color, in: Capsule())
    }

    // MARK: Review and done

    private var reviewPage: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let lead = attachments.first?.thumbnail {
                    Image(uiImage: lead).resizable().scaledToFill().frame(height: 190).clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                        .overlay(alignment: .bottomTrailing) { if attachments.count > 1 { chip("+\(attachments.count - 1)").padding(8) } }
                }
                TextField("Give it a title (optional)", text: $draft.title).font(.title3.bold())
                DatePicker("When", selection: Binding(get: { draft.occurredAt }, set: { draft.occurredAt = $0; dateChosenByHand = true }), displayedComponents: .date)
                TextField("Where (optional)", text: $draft.place)
                TextField("Who was there (comma separated)", text: $people)
                if let song = draft.songs.first { songRow(song, trailing: AnyView(EmptyView())) }
                if !draft.text.isEmpty {
                    Button { move(to: .story) } label: {
                        Text(draft.text).font(.system(size: 18, design: .serif)).foregroundStyle(theme.ink.color).multilineTextAlignment(.leading).lineLimit(6)
                    }.buttonStyle(.plain)
                }
                let tags = MemoryDraft.normalizedTags(draft.tags + MemoryDraft.storyTags(draft.text))
                if !tags.isEmpty { ScrollView(.horizontal, showsIndicators: false) { HStack(spacing: 6) { ForEach(tags, id: \.self) { chip("#" + $0) } } } }
                suggestedTags
            }
            .padding(18).background(theme.card.color, in: RoundedRectangle(cornerRadius: JukeRadius.card, style: .continuous))
            .padding(.horizontal, 20).padding(.vertical, 8)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    /// Tags from earlier memories, one tap to add.
    @ViewBuilder private var suggestedTags: some View {
        let known = model.memories.reusableTags.filter { tag in !draft.tags.contains { $0.caseInsensitiveCompare(tag) == .orderedSame } }.prefix(12)
        if !known.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(Array(known), id: \.self) { tag in
                        Button { draft.tags = MemoryDraft.normalizedTags(draft.tags + [tag]) } label: { Label("#" + tag, systemImage: "plus").font(.caption.weight(.medium)) }
                            .buttonStyle(.bordered).controlSize(.small)
                    }
                }
            }
        }
    }

    private var completePage: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "checkmark.circle.fill").font(.system(size: 72)).foregroundStyle(theme.accent.color)
                .symbolEffect(.bounce, options: reduceMotion ? .nonRepeating.speed(0) : .nonRepeating)
            Text(draft.displayTitleForPreview).font(.title3.weight(.semibold)).foregroundStyle(theme.ink.color).multilineTextAlignment(.center).padding(.horizontal, 30)
            Spacer()
        }
        .frame(maxWidth: .infinity).accessibilityIdentifier("memory.complete")
    }

    // MARK: Actions

    private func move(to target: MemoryJourneyFlow.Step) {
        let current = flow.order.firstIndex(of: flow.step) ?? 0, goal = flow.order.firstIndex(of: target) ?? 0
        forward = goal > current
        withAnimation(gentle) { flow.jump(to: target) }
    }

    private func goBack() { forward = false; withAnimation(gentle) { flow.back() } }

    private func advance() async {
        error = nil
        switch flow.step {
        case .review: await save()
        case .complete: onClose()
        default: forward = true; withAnimation(gentle) { flow.next() }
        }
    }

    private func search() async {
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let token = model.session?.accessToken else { return }
        searching = true; error = nil
        defer { searching = false }
        do { results = try await catalog.search(text, kind: "tracks", token: token) }
        catch is CancellationError { return }
        catch { self.error = (error as? LocalizedError)?.errorDescription ?? "Search is unavailable right now." }
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
                guard gate.shouldKeepLateUpload() else { await model.memories.discardMedia([media]); return }
                if !dateChosenByHand, attachments.isEmpty, let date = MemoryJourneyFlow.captureDate(fromImageData: data) { draft.occurredAt = date }
                attachments.append(Attachment(media: media, thumbnail: type?.conforms(to: .image) == false ? nil : UIImage(data: data)?.preparingThumbnail(of: CGSize(width: 480, height: 480))))
            } catch { self.error = (error as? LocalizedError)?.errorDescription ?? "That attachment could not be added." }
        }
    }

    private func remove(_ item: Attachment) {
        attachments.removeAll { $0.id == item.id }
        Task { await model.memories.discardMedia([item.media]) }
    }

    private func discard() {
        let media = attachments.map(\.media)
        guard !media.isEmpty else { return }
        Task { await model.memories.discardMedia(media) }
    }

    private func save() async {
        var value = MemoryJourneyFlow.savableDraft(draft, attachmentIDs: attachments.map(\.media.id))
        value.people = people.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        value.tags = MemoryDraft.normalizedTags(value.tags + MemoryDraft.storyTags(value.text))
        if let message = value.validationMessage { error = message; return }
        saving = true
        defer { saving = false }
        do {
            _ = try await model.memories.save(value)
            didSave = true
            forward = true
            withAnimation(gentle) { flow.complete() }
        } catch { self.error = error.localizedDescription }
    }
}

private extension MemoryDraft {
    var displayTitleForPreview: String { title.isEmpty ? (songs.first?.title ?? "Saved") : title }
}
