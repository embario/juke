import SwiftUI
import AVKit

/// Memories as a single card: one memory at a time, a tilted photo print on
/// the left, its date · place, title, story, song ("Play the moment") and
/// chips on the right, and ‹ n of N › to flip between memories. The card and
/// page colours follow the current memory's song artwork.
///
/// Everything the old catalog did is still here: search, connection threads,
/// "On this day", oldest/newest order (in the index popover), refresh, all
/// photos and videos (click the print), every song, people, place and tag
/// editing. "New memory" opens the guided composer inside the same card.
struct MemoriesView: View {
    @Environment(AppModel.self) private var app
    @Environment(MemoryStore.self) private var store
    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var isComposing = false
    @State private var composerStartsWithSong = false
    @State private var browser = MemoryBrowser()
    @State private var search = ""
    @State private var connection: MemoryInsights.Connection?
    @State private var oldestFirst = false
    @State private var showingIndex = false
    @State private var mediaMemory: MusicMemory?
    @State private var showingOnThisDay = false
    /// The memories the card flips through, recomputed only when the
    /// memories, search, thread or order change.
    @State private var filtered: [MusicMemory] = []
    @FocusState private var cardFocused: Bool
    @FocusState private var searchFocused: Bool

    private struct FilterKey: Equatable {
        let memories: [MusicMemory]
        let search: String
        let connection: String?
        let oldestFirst: Bool
    }

    private var filterKey: FilterKey {
        FilterKey(memories: store.memories, search: search, connection: connection?.id, oldestFirst: oldestFirst)
    }

    private func computeFiltered() -> [MusicMemory] {
        store.memories.filter { memory in
            (connection == nil || connection!.memoryIDs.contains(memory.id)) &&
            (search.isEmpty || ([memory.title, memory.text, memory.place] + memory.tags + memory.people + memory.songs.map { "\($0.title) \($0.artist)" }).joined(separator: " ").localizedCaseInsensitiveContains(search))
        }.sorted { oldestFirst ? $0.occurredAt < $1.occurredAt : $0.occurredAt > $1.occurredAt }
    }

    private var current: MusicMemory? {
        browser.currentID.flatMap { id in store.memories.first { $0.id == id } }
    }

    var body: some View {
        Group {
            if isComposing {
                JukeCard(padding: EdgeInsets(top: 10, leading: 10, bottom: 10, trailing: 10)) {
                    MemoryComposerView(
                        startWithSong: composerStartsWithSong,
                        onSaved: { id in
                            search = ""; connection = nil
                            browser.select(id)
                            isComposing = false
                        },
                        onClose: { isComposing = false }
                    )
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
                .frame(maxWidth: 1040, maxHeight: .infinity)
                .transition(.opacity)
            } else {
                JukeCard(padding: EdgeInsets(top: 22, leading: 32, bottom: 26, trailing: 32)) {
                    browserCard
                }
                .frame(width: JukeMetrics.memoriesCardWidth)
                .frame(maxHeight: 620)
                .transition(.opacity)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .animation(JukeMotion.navigationIn(reduceMotion: reduceMotion), value: isComposing)
        .onChange(of: isComposing) { _, composing in
            if composing { composerStartsWithSong = app.detection.track != nil }
            app.memoryJourneyActive = composing
            syncArtwork()
        }
        .onChange(of: filterKey, initial: true) { _, _ in
            filtered = computeFiltered()
            browser.update(ids: filtered.map(\.id))
        }
        .onChange(of: current?.songs.first?.artworkURL, initial: true) { _, _ in syncArtwork() }
        .onChange(of: app.lock.isLocked) { _, _ in syncArtwork() }
        .onDisappear {
            app.memoryJourneyActive = false
            app.artworkOverride = nil
        }
        .sheet(item: $mediaMemory) { memory in MemoryMediaSheet(memory: memory) }
    }

    /// The card follows the shown memory's song; the composer keeps its own
    /// accent, and nothing of a memory shows through the lock screen.
    private func syncArtwork() {
        app.artworkOverride = isComposing || app.lock.isLocked ? nil : current?.songs.first?.artworkURL
    }

    // MARK: Browsing card

    private var browserCard: some View {
        VStack(alignment: .leading, spacing: 18) {
            toolbar
            if let error = store.error {
                HStack {
                    Label(error, systemImage: "wifi.exclamationmark")
                    Spacer()
                    Button("Try again") { Task { await store.refresh() } }.buttonStyle(.plain).foregroundStyle(theme.accent.color)
                }
                .font(JukeFont.body(13)).padding(.horizontal, 14).padding(.vertical, 10).jukeWell(cornerRadius: JukeRadius.tile)
            }
            if store.isLoading && store.memories.isEmpty {
                ProgressView("Opening your memories…").frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let memory = current {
                memoryPage(memory)
            } else if store.memories.isEmpty {
                invitation
            } else {
                noMatches
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .focusable()
        .focused($cardFocused)
        .focusEffectDisabled()
        .overlay {
            // The card's own focus ring: ← and → flip while it is focused.
            RoundedRectangle(cornerRadius: JukeRadius.card - 8, style: .continuous)
                .strokeBorder(theme.accent.color.opacity(cardFocused ? 0.7 : 0), lineWidth: 2)
                .padding(-10)
                .allowsHitTesting(false)
        }
        .onKeyPress(.leftArrow) { arrowFlip(forward: false) }
        .onKeyPress(.rightArrow) { arrowFlip(forward: true) }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("memory.catalog")
    }

    private var toolbar: some View {
        HStack(spacing: 10) {
            Button { isComposing = true } label: {
                Text(store.insights.question).lineLimit(1).truncationMode(.tail)
            }
            .buttonStyle(.plain)
            .font(JukeFont.body(14))
            .foregroundStyle(theme.sub.color)
            .help("This brings something back: start a memory")
            .accessibilityIdentifier("memory.nudge")
            Spacer(minLength: 12)
            if let connection {
                Button { self.connection = nil } label: { Label("\(connection.label)", systemImage: "xmark") }
                    .buttonStyle(MemoryChipButtonStyle(selected: true))
                    .help("Clear this thread")
            }
            searchField
            if !store.insights.connections.isEmpty {
                Menu {
                    ForEach(store.insights.connections) { item in
                        Button { connection = item } label: {
                            Label("\(item.label) · \(item.count)", systemImage: item.kind == "person" ? "person.2" : item.kind == "place" ? "mappin" : "music.note")
                        }
                    }
                } label: { Image(systemName: "point.3.connected.trianglepath.dotted") }
                    .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                    .help("Threads through your memories")
                    .accessibilityLabel("Threads through your memories")
            }
            if !onThisDay.isEmpty {
                Button { showingOnThisDay.toggle() } label: {
                    Image(systemName: "clock.arrow.circlepath")
                }
                .buttonStyle(.plain).frame(width: 32, height: 32)
                .help("On this day")
                .accessibilityLabel("On this day")
                .accessibilityIdentifier("memory.onThisDay")
                .popover(isPresented: $showingOnThisDay, arrowEdge: .bottom) { onThisDayList }
            }
            Button { showingIndex.toggle() } label: { Image(systemName: "list.bullet") }
                .buttonStyle(.plain).frame(width: 32, height: 32)
                .help("All memories")
                .accessibilityLabel("All memories")
                .accessibilityIdentifier("memory.index")
                .popover(isPresented: $showingIndex, arrowEdge: .bottom) { index }
            Button { Task { await store.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                .buttonStyle(.plain).frame(width: 32, height: 32)
                .help("Refresh memories")
                .accessibilityLabel("Refresh memories")
            Button { isComposing = true } label: { Label("New memory", systemImage: "plus") }
                .buttonStyle(JukeAccentButtonStyle())
                .accessibilityIdentifier("memory.new")
        }
        .foregroundStyle(theme.ink.color)
    }

    private var searchField: some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass").foregroundStyle(theme.sub.color)
            TextField("Song, person, place, tag", text: $search)
                .textFieldStyle(.plain)
                .focused($searchFocused)
                .accessibilityIdentifier("memory.search")
            if !search.isEmpty {
                Button { search = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(theme.sub.color) }
                    .buttonStyle(.plain).help("Clear search")
            }
        }
        .font(JukeFont.body(13))
        .padding(.horizontal, 12)
        .frame(width: 210, height: 34)
        .jukeWell(cornerRadius: 17)
    }

    // MARK: One memory

    private func memoryPage(_ memory: MusicMemory) -> some View {
        HStack(alignment: .top, spacing: 36) {
            MemoryPrint(memory: memory) { mediaMemory = memory }
                .frame(width: 320, height: 400)
                .id(memory.id)
                .transition(printTransition)
            VStack(alignment: .leading, spacing: 0) {
                MemoryPageDetails(memory: memory, anniversary: anniversaryLabel(memory))
                    .id(memory.id)
                    .transition(detailsTransition)
                Spacer(minLength: 16)
                pager
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .padding(.top, 6)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    /// The print slides in from the side it came from, settling at its -1.5° tilt.
    private var printTransition: AnyTransition {
        guard !reduceMotion else { return .opacity }
        let sign: CGFloat = browser.direction == .forward ? 1 : -1
        return .asymmetric(
            insertion: .modifier(active: PrintFlip(progress: 1, sign: sign), identity: PrintFlip(progress: 0, sign: sign)),
            removal: .opacity.animation(.easeOut(duration: 0.15))
        )
    }

    private var detailsTransition: AnyTransition {
        guard !reduceMotion else { return .opacity }
        return .asymmetric(insertion: .opacity.combined(with: .offset(y: 8)), removal: .opacity.animation(.easeOut(duration: 0.12)))
    }

    private var pager: some View {
        HStack(spacing: 6) {
            Button { flip(forward: false) } label: { Image(systemName: "chevron.left") }
                .buttonStyle(MemoryRoundButtonStyle())
                .keyboardShortcut("[", modifiers: .command)
                .help("Previous memory (⌘[)")
                .disabled(!browser.canFlip)
                .accessibilityLabel("Previous memory")
                .accessibilityIdentifier("memory.previous")
            Text(browser.positionLabel)
                .font(JukeFont.body(14)).monospacedDigit()
                .foregroundStyle(theme.sub.color)
                .frame(minWidth: 64)
                .accessibilityIdentifier("memory.position")
            Button { flip(forward: true) } label: { Image(systemName: "chevron.right") }
                .buttonStyle(MemoryRoundButtonStyle())
                .keyboardShortcut("]", modifiers: .command)
                .help("Next memory (⌘])")
                .disabled(!browser.canFlip)
                .accessibilityLabel("Next memory")
                .accessibilityIdentifier("memory.following")
        }
    }

    /// Arrow keys flip only when the card itself has focus, never while typing a search.
    private func arrowFlip(forward: Bool) -> KeyPress.Result {
        guard cardFocused, !searchFocused, current != nil else { return .ignored }
        flip(forward: forward)
        return .handled
    }

    private func flip(forward: Bool) {
        guard browser.canFlip else { return }
        withAnimation(reduceMotion ? nil : JukeMotion.easeOutSoft(0.52)) {
            if forward { browser.next() } else { browser.previous() }
        }
    }

    // MARK: Empty states

    private var invitation: some View {
        HStack(alignment: .center, spacing: 36) {
            MemoryPrint(memory: nil, onOpen: nil).frame(width: 320, height: 400)
            VStack(alignment: .leading, spacing: 14) {
                Text("A song can hold a whole story.").font(JukeFont.display(34, weight: .bold)).tracking(-0.8)
                Text(store.insights.question).font(JukeFont.body(17)).lineSpacing(4)
                if let track = app.detection.track {
                    Label("Listening to \(track.title) · \(track.artist)", systemImage: "waveform")
                        .font(JukeFont.body(14)).foregroundStyle(theme.sub.color)
                }
                Text("Save a song, a face, a place, or just a few words. Start wherever the memory begins.")
                    .font(JukeFont.body(15)).foregroundStyle(theme.sub.color)
                Button("Create your first memory") { isComposing = true }
                    .buttonStyle(JukeAccentButtonStyle())
                    .padding(.top, 6)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var noMatches: some View {
        VStack(spacing: 12) {
            Text("No memories found").font(JukeFont.display(24))
            Text("Try another word or clear the thread.").foregroundStyle(theme.sub.color)
            Button("Show every memory") { search = ""; connection = nil }.buttonStyle(JukeWellButtonStyle())
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: Index

    /// A quiet chronological index: jump straight to any memory.
    private var index: some View {
        let calendar = Calendar.current
        let months = Dictionary(grouping: filtered) { calendar.dateInterval(of: .month, for: $0.occurredAt)?.start ?? $0.occurredAt }
        let keys = months.keys.sorted { oldestFirst ? $0 < $1 : $0 > $1 }
        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("\(filtered.count) memories").font(JukeFont.body(13, weight: .semibold))
                Spacer()
                Toggle("Oldest first", isOn: $oldestFirst).toggleStyle(.checkbox).font(JukeFont.body(13))
            }
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    ForEach(keys, id: \.self) { month in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(month.formatted(.dateTime.month(.wide).year()))
                                .font(JukeFont.body(12, weight: .bold)).foregroundStyle(theme.sub.color)
                            ForEach(months[month] ?? []) { memory in
                                Button {
                                    withAnimation(reduceMotion ? nil : JukeMotion.easeOutSoft(0.52)) { browser.select(memory.id) }
                                    showingIndex = false
                                } label: {
                                    HStack(spacing: 8) {
                                        Text(memory.occurredAt.formatted(.dateTime.day())).monospacedDigit().frame(width: 22, alignment: .trailing).foregroundStyle(theme.sub.color)
                                        Text(memory.displayTitle).lineLimit(1)
                                        Spacer(minLength: 4)
                                        if let song = memory.songs.first { Text(song.title).lineLimit(1).foregroundStyle(theme.sub.color) }
                                    }
                                    .font(JukeFont.body(14))
                                    .padding(.vertical, 5).padding(.horizontal, 6)
                                    .background(memory.id == browser.currentID ? theme.accentSoft.color : .clear, in: RoundedRectangle(cornerRadius: 8))
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                                .accessibilityIdentifier("memory.card.\(memory.title)")
                            }
                        }
                    }
                }
            }
        }
        .padding(16)
        .frame(width: 380, height: 420)
    }

    // MARK: On this day

    /// Memories from this week in earlier years, resurfaced like a journal falling open.
    private var onThisDay: [MusicMemory] {
        store.memories.filter { anniversaryYears($0) != nil }.sorted { $0.occurredAt > $1.occurredAt }
    }

    /// Every memory from this week in earlier years.
    private var onThisDayList: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("On this day").font(JukeFont.body(13, weight: .semibold))
            ForEach(onThisDay) { memory in
                Button {
                    search = ""; connection = nil
                    withAnimation(reduceMotion ? nil : JukeMotion.easeOutSoft(0.52)) { browser.select(memory.id) }
                    showingOnThisDay = false
                } label: {
                    HStack(spacing: 8) {
                        Text(anniversaryLabel(memory) ?? "").foregroundStyle(theme.sub.color)
                        Text(memory.displayTitle).lineLimit(1)
                        Spacer(minLength: 0)
                    }
                    .font(JukeFont.body(14)).padding(.vertical, 4).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("memory.onThisDay.\(memory.id)")
            }
        }
        .padding(16)
        .frame(width: 360)
    }

    private func anniversaryYears(_ memory: MusicMemory) -> Int? {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        let years = calendar.component(.year, from: today) - calendar.component(.year, from: memory.occurredAt)
        guard years > 0, let anniversary = calendar.date(byAdding: .year, value: years, to: calendar.startOfDay(for: memory.occurredAt)),
              abs(calendar.dateComponents([.day], from: today, to: anniversary).day ?? 99) <= 3 else { return nil }
        return years
    }

    private func anniversaryLabel(_ memory: MusicMemory) -> String? {
        anniversaryYears(memory).map { $0 == 1 ? "A year ago this week" : "\($0) years ago this week" }
    }
}

/// Insertion for the photo print: from opacity 0, -4° and 16pt to the side
/// (the prototype's `rotate(-4deg) translateX(-16px)`) to its resting tilt.
private struct PrintFlip: ViewModifier {
    let progress: Double
    let sign: CGFloat

    func body(content: Content) -> some View {
        content
            .opacity(1 - progress)
            .rotationEffect(.degrees(-2.5 * progress * Double(sign)))
            .offset(x: -16 * progress * sign)
    }
}

/// The photo print: paper-coloured frame, a wide bottom margin and a slight tilt.
private struct MemoryPrint: View {
    @Environment(\.jukeTheme) private var theme
    let memory: MusicMemory?
    let onOpen: (() -> Void)?

    var body: some View {
        if memory?.media.isEmpty == false, let onOpen {
            Button(action: onOpen) { paper }
                .buttonStyle(.plain)
                .help("See every photo and video")
                .accessibilityLabel(memory.map { "Photos for \($0.displayTitle)" } ?? "Photos")
                .accessibilityIdentifier("memory.print")
        } else {
            paper
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(memory.map { "Photo print for \($0.displayTitle), no photos" } ?? "Empty photo print")
                .accessibilityIdentifier("memory.print")
        }
    }

    private var paper: some View {
        let media = memory?.media.first
        return VStack(spacing: 0) {
            Group {
                if let media { MemoryMediaView(media: media, compact: true) }
                else { placeholder }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .clipShape(RoundedRectangle(cornerRadius: 2))
            HStack {
                if let memory, !memory.place.isEmpty {
                    Text(memory.place).lineLimit(1)
                }
                Spacer()
                if let count = memory?.media.count, count > 1 { Text("+\(count - 1)") }
            }
            .font(JukeFont.body(12, weight: .semibold))
            .foregroundStyle(Color.black.opacity(0.45))
            .frame(height: 32)
            .padding(.horizontal, 2)
        }
        .padding(EdgeInsets(top: 12, leading: 12, bottom: 0, trailing: 12))
        .padding(.bottom, 6)
        .background(theme.print.color, in: RoundedRectangle(cornerRadius: 4))
        .shadow(color: .black.opacity(0.22), radius: 20, y: 16)
        .rotationEffect(.degrees(-1.5))
        .contentShape(Rectangle())
    }

    /// No photo: a soft field in the song's colour, so the print still feels like a print.
    private var placeholder: some View {
        ZStack(alignment: .bottomLeading) {
            LinearGradient(colors: [theme.accent.color.opacity(0.55), theme.base.color.opacity(0.8)], startPoint: .top, endPoint: .bottom)
            if let url = memory?.songs.first?.artworkURL {
                AsyncImage(url: url) { image in image.resizable().scaledToFill().opacity(0.85) } placeholder: { Color.clear }
            }
            Image(systemName: memory?.songs.isEmpty == false ? "waveform" : "quote.opening")
                .font(.system(size: 40, weight: .light))
                .foregroundStyle(.white.opacity(0.85))
                .padding(16)
        }
        .clipped()
    }
}

/// Date · place, title, story, songs, chips and tag editing for one memory.
private struct MemoryPageDetails: View {
    @Environment(AppModel.self) private var app
    @Environment(MemoryStore.self) private var store
    @Environment(\.jukeTheme) private var theme
    let memory: MusicMemory
    let anniversary: String?
    @State private var editingTags = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let anniversary {
                    Text(anniversary.uppercased()).font(JukeFont.body(11, weight: .bold)).tracking(1.2).foregroundStyle(theme.accent.color)
                }
                Text([memory.occurredAt.formatted(date: .abbreviated, time: .omitted), memory.place.isEmpty ? nil : memory.place].compactMap { $0 }.joined(separator: " · "))
                    .font(JukeFont.body(14)).foregroundStyle(theme.sub.color)
                Text(memory.displayTitle)
                    .font(JukeFont.display(34, weight: .bold)).tracking(-0.8)
                    .fixedSize(horizontal: false, vertical: true)
                if !memory.text.isEmpty {
                    Text(memory.text).font(JukeFont.body(17)).lineSpacing(5).textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ForEach(memory.songs) { song in songChip(song) }
                if let error = app.detection.errorMessage, !memory.songs.isEmpty {
                    Label(error, systemImage: "info.circle").font(JukeFont.body(12)).foregroundStyle(theme.sub.color)
                }
                chips
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.trailing, 4)
        }
        .scrollIndicators(.automatic)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("memory.detail")
        .sheet(isPresented: $editingTags) { MemoryTagEditor(memory: memory) }
    }

    /// The song in a well with "Play the moment" (the saved segment, or the whole song).
    private func songChip(_ song: MemorySong) -> some View {
        HStack(spacing: 12) {
            AsyncImage(url: song.artworkURL) { image in image.resizable().scaledToFill() } placeholder: {
                ZStack { theme.accentSoft.color; Image(systemName: "music.note").foregroundStyle(theme.accent.color) }
            }
            .frame(width: 48, height: 48).clipShape(RoundedRectangle(cornerRadius: 8)).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(song.title).font(JukeFont.body(15, weight: .bold)).lineLimit(1)
                Text([song.artist, song.segmentDescription.map { "the moment \($0)" }, song.provider == "spotify" ? "Spotify" : "Apple Music"].compactMap { $0 }.joined(separator: " · "))
                    .font(JukeFont.body(13)).foregroundStyle(theme.sub.color).lineLimit(1)
            }
            Spacer(minLength: 8)
            if let url = song.playbackURL, ["https", "spotify", "music"].contains(url.scheme ?? "") {
                Link(destination: url) { Image(systemName: "arrow.up.right") }
                    .foregroundStyle(theme.sub.color)
                    .help("Open in \(song.provider == "spotify" ? "Spotify" : "Apple Music")")
            }
            Button("Play") {
                Task { await app.detection.playMemorySong(provider: song.provider, providerID: song.providerID, playbackURL: song.playbackURL, title: song.title, artist: song.artist, startSeconds: song.startSeconds, endSeconds: song.endSeconds) }
            }
            .buttonStyle(JukeAccentButtonStyle())
            .disabled(app.detection.isPlaybackBusy)
            .accessibilityLabel(song.segmentDescription == nil ? "Play \(song.title)" : "Play the moment")
            .accessibilityIdentifier("memory.playMoment")
        }
        .padding(10)
        .jukeWell()
    }

    private var chips: some View {
        FlowLayout(spacing: 6) {
            ForEach(memory.people, id: \.self) { person in MemoryChip(text: person, systemImage: "person") }
            ForEach(memory.tags, id: \.self) { tag in MemoryChip(text: "#" + tag, systemImage: nil) }
            Button { editingTags = true } label: { Label(memory.tags.isEmpty ? "Add tags" : "Edit tags", systemImage: "plus") }
                .buttonStyle(MemoryChipButtonStyle(selected: false))
                .accessibilityIdentifier("memory.editTags")
        }
    }
}

private struct MemoryChip: View {
    @Environment(\.jukeTheme) private var theme
    let text: String
    let systemImage: String?

    var body: some View {
        HStack(spacing: 4) {
            if let systemImage { Image(systemName: systemImage).font(.system(size: 10)) }
            Text(text).lineLimit(1)
        }
        .font(JukeFont.body(13))
        .padding(.horizontal, 12).padding(.vertical, 6)
        .overlay(Capsule().strokeBorder(theme.line, lineWidth: 1))
    }
}

struct MemoryChipButtonStyle: ButtonStyle {
    @Environment(\.jukeTheme) private var theme
    var selected: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(JukeFont.body(13, weight: .semibold))
            .foregroundStyle(theme.ink.color)
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(selected ? theme.accentSoft.color : .clear, in: Capsule())
            .overlay(Capsule().strokeBorder(theme.line, lineWidth: 1))
            .opacity(configuration.isPressed ? 0.7 : 1)
            .contentShape(Capsule())
    }
}

/// The prototype's 44pt round outline buttons (‹ and ›).
private struct MemoryRoundButtonStyle: ButtonStyle {
    @Environment(\.jukeTheme) private var theme
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 16, weight: .semibold))
            .foregroundStyle(theme.ink.color)
            .frame(width: JukeMetrics.minimumHitTarget, height: JukeMetrics.minimumHitTarget)
            .overlay(Circle().strokeBorder(theme.line, lineWidth: 1))
            .opacity(isEnabled ? (configuration.isPressed ? 0.6 : 1) : 0.35)
            .contentShape(Circle())
    }
}

/// Edit a memory's tags; the old detail page's sheet, unchanged in behaviour.
private struct MemoryTagEditor: View {
    @Environment(AppModel.self) private var app
    @Environment(MemoryStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @Environment(\.jukeTheme) private var theme
    let memory: MusicMemory
    @State private var tagsText = ""
    @State private var error: String?
    @State private var saving = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Make these tags yours").font(JukeFont.display(22))
            Text("Add tags or remove any suggestions. Separate tags with commas; they’ll be available for your next memory.").foregroundStyle(theme.sub.color)
            TextField("Tags", text: $tagsText).textFieldStyle(.roundedBorder).accessibilityIdentifier("memory.tagEditor")
            if memory.classification.status != "complete" {
                Text("Automatic tags aren’t connected yet. Your own tags are saved to your profile.").font(JukeFont.body(12)).foregroundStyle(theme.sub.color)
            }
            if let error { Text(error).foregroundStyle(theme.accent.color) }
            HStack {
                Button("Cancel") { dismiss() }.disabled(saving)
                Spacer()
                Button("Save tags") {
                    saving = true
                    Task {
                        defer { saving = false }
                        do { try await store.updateTags(tagsText.components(separatedBy: ","), for: memory); dismiss() }
                        catch { self.error = error.localizedDescription }
                    }
                }
                .buttonStyle(JukeAccentButtonStyle()).disabled(saving).accessibilityIdentifier("memory.saveTags")
            }
        }
        .padding(28).frame(width: 490)
        .onAppear { tagsText = memory.tags.joined(separator: ", ") }
        .disabled(app.lock.isLocked)
        .accessibilityHidden(app.lock.isLocked)
        .overlay { if app.lock.isLocked { LockedView() } }
    }
}

/// Every photo and video of a memory, full size.
private struct MemoryMediaSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    let memory: MusicMemory

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(memory.displayTitle).font(JukeFont.display(22))
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
            ScrollView {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 280))], spacing: 16) {
                    ForEach(memory.media) { media in
                        MemoryMediaView(media: media, compact: false).frame(height: 260).clipShape(RoundedRectangle(cornerRadius: JukeRadius.tile))
                    }
                }
            }
        }
        .padding(24)
        .frame(width: 720, height: 560)
        .disabled(app.lock.isLocked)
        .accessibilityHidden(app.lock.isLocked)
        .overlay { if app.lock.isLocked { LockedView() } }
        .accessibilityIdentifier("memory.media")
    }
}

struct MemoryMediaView: View {
    @Environment(AppModel.self) private var app
    @Environment(MemoryStore.self) private var store
    @Environment(\.jukeTheme) private var theme
    let media: MemoryMedia
    let compact: Bool
    @State private var image: NSImage?
    @State private var player: AVPlayer?
    @State private var error: String?
    var body: some View {
        ZStack {
            Rectangle().fill(theme.well.color)
            if let image { Image(nsImage: image).resizable().aspectRatio(contentMode: compact ? .fill : .fit) }
            else if let player { VideoPlayer(player: player).disabled(compact) }
            else if let error { VStack { Image(systemName: "photo.badge.exclamationmark"); Text(error).font(.caption).multilineTextAlignment(.center) }.padding() }
            else { ProgressView() }
            if compact && media.kind == "video" { Image(systemName: "play.circle.fill").font(.largeTitle).foregroundStyle(.white) }
        }
        .clipped()
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
