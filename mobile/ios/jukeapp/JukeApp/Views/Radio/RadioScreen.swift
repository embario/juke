import SwiftUI

/// Tracks the last issue dismissed by the listener. An identical issue stays
/// suppressed across repeated refreshes; a changed or cleared issue resets it,
/// and so does every press that fails again (the listener asked, so they are told).
struct RadioIssuePresentation: Equatable {
    private(set) var dismissedIssue: RadioIssue?
    /// `RadioController.failedPresses` as last seen.
    private(set) var seenPresses = 0
    /// Failed presses in a row that ended in the issue now showing.
    private(set) var tries = 0
    private var triedIssue: RadioIssue?

    func visibleIssue(for currentIssue: RadioIssue?) -> RadioIssue? {
        currentIssue == dismissedIssue ? nil : currentIssue
    }

    mutating func dismiss(_ issue: RadioIssue) {
        dismissedIssue = issue
    }

    mutating func observe(_ currentIssue: RadioIssue?) {
        // Repeated observations of the same dismissed issue are normal polls.
        // A nil or different value means the old issue has cleared or changed.
        if currentIssue != dismissedIssue { dismissedIssue = nil }
        if currentIssue != triedIssue { tries = 0; triedIssue = currentIssue }
    }

    /// A press just failed with `currentIssue`. Returns true when the banner must (re)appear or nudge.
    @discardableResult
    mutating func observePress(_ presses: Int, issue currentIssue: RadioIssue?) -> Bool {
        guard presses != seenPresses else { return false }
        seenPresses = presses
        guard let currentIssue else { return false }
        if currentIssue != triedIssue { tries = 0; triedIssue = currentIssue }
        tries += 1
        dismissedIssue = nil
        return true
    }

    /// "Tried 3 times": only from the second failed press on, so one failure reads as before.
    var triesCaption: String? { tries >= 2 ? "Tried \(tries) times" : nil }
}

/// Radio on iPhone: one card with the sleeve, transport, reactions and the
/// station strip. Touch gestures (vinyl, FM dial) come in later slices.
struct RadioScreen: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var issuePresentation = RadioIssuePresentation()

    private var isNewStation: Bool {
        if case .newStation = model.coordinator.radioRoute { true } else { false }
    }

    var body: some View {
        let radio = model.radio
        let issue = previewIssue ?? radio.issue
        // Flicking the dial to "+ New" eases the card away and the wizard in (and back again).
        ZStack {
            if case .newStation(let draft) = model.coordinator.radioRoute {
                NewStationScreen(draft: draft)
                    .transition(reduceMotion ? .opacity : .move(edge: .bottom).combined(with: .opacity))
            } else if !radio.hasTunedIn {
                FirstRunCard().transition(.opacity)
            } else {
                NowPlayingCard()
                    .transition(reduceMotion ? .opacity : .scale(scale: 0.94).combined(with: .opacity))
            }
        }
        .animation(reduceMotion ? nil : .smooth(duration: 0.5), value: isNewStation)
        .navigationTitle(model.coordinator.radioRoute == .nowPlaying ? "Radio" : "New station")
        .navigationBarTitleDisplayMode(.inline)
        .background(VibeBackground(atmosphere: model.atmosphere))
        .overlay(alignment: .top) {
            if let issue = issuePresentation.visibleIssue(for: issue) {
                ConnectionIssueOverlay(issue: issue, triesCaption: issuePresentation.triesCaption, nudge: issuePresentation.seenPresses) {
                    withAnimation(reduceMotion ? nil : .snappy) { issuePresentation.dismiss(issue) }
                }
                .padding(.horizontal, 16)
                .padding(.top, 8)
                .zIndex(1)
                .transition(reduceMotion ? .opacity : .move(edge: .top).combined(with: .opacity))
            }
        }
        .animation(reduceMotion ? nil : .snappy(duration: 0.25), value: issuePresentation.visibleIssue(for: issue))
        .onChange(of: issue) { _, current in issuePresentation.observe(current) }
        // Every failed Next is answered, including the same answer as last time and one already dismissed.
        .onChange(of: radio.failedPresses, initial: true) { _, presses in issuePresentation.observePress(presses, issue: issue) }
    }

    /// A deterministic connection-error state for simulator screenshots.
    private var previewIssue: RadioIssue? {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--uitesting-radio-error") {
            return .unavailable("Juke could not be reached. Check your connection and try again.")
        }
        #endif
        return nil
    }
}

private struct FirstRunCard: View {
    @Environment(VibeAppModel.self) private var model

    var body: some View {
        VStack(spacing: 18) {
            Spacer()
            Image(systemName: "dot.radiowaves.left.and.right").font(.system(size: 54)).foregroundStyle(model.atmosphere.primary)
            Text("Your station is ready").font(.title.bold())
            Text("Juke picks songs from your taste and plays them on Spotify, one after another.")
                .multilineTextAlignment(.center).foregroundStyle(.secondary)
            Button { Task { await model.radio.tuneIn() } } label: {
                Label("Tune in", systemImage: "play.fill").frame(maxWidth: 260)
            }
            .buttonStyle(.borderedProminent).controlSize(.large).tint(model.atmosphere.primary)
            .disabled(model.radio.isBusy)
            Spacer()
        }.padding(24)
    }
}

private struct NowPlayingCard: View {
    @Environment(VibeAppModel.self) private var model
    @State private var visibleHeight: CGFloat = 900
    @State private var containerWidth: CGFloat = 390
    @State private var detail: DetailRoute?
    @State private var tunerOpen = false
    @ScaledMetric(relativeTo: .body) private var tunerReserve = TunerDrawerStyle.reserve

    var body: some View {
        let radio = model.radio
        ScrollView {
            VStack(spacing: 10) {
                StationHeader()
                if radio.isPutAway { PutAwayCard() }
                SleeveAndRecord(track: radio.track, side: RadioLayout.sleeveSide(visibleHeight: visibleHeight, containerWidth: containerWidth))
                VStack(spacing: 4) {
                    Text(radio.track?.title ?? "Nothing playing").font(.title2.bold()).multilineTextAlignment(.center).lineLimit(2)
                    // The artist and album open their screens (catalog, bio, tracklist) in a sheet.
                    detailLink(radio.track.flatMap(DetailRoute.artist(of:)), id: "radio.artistDetails") {
                        Text(radio.track?.artist ?? "Press play to start your station").foregroundStyle(.secondary).lineLimit(1)
                    }
                    if let album = radio.track?.album {
                        detailLink(radio.track.flatMap(DetailRoute.album(of:)), id: "radio.albumDetails") {
                            Text(album).font(.caption).foregroundStyle(.tertiary).lineLimit(1)
                        }
                    }
                    // "Paused" or "Waiting for Spotify…"; a missing device is explained by the floating issue banner.
                    if radio.status == .paused || radio.status == .resuming, let caption = radio.status.caption {
                        Text(caption).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                            .accessibilityIdentifier("radio.status")
                    }
                }
                ProgressScrubber()
                Transport()
                ReactionEmojiSlider()
                if let notice = radio.notice { Text(notice).font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center) }
                if radio.isPausedForEpisode {
                    Button("Resume station") { Task { await radio.togglePlayPause() } }.buttonStyle(.borderedProminent).accessibilityIdentifier("radio.resumeStation")
                }
            }
            .padding(.horizontal, 20).padding(.vertical, 12)
        }
        // Room under the content for the tuner's closed handle. Opened, the drawer rises over the lower part of the card
        // (it never resizes the vinyl).
        .contentMargins(.bottom, tunerReserve, for: .scrollContent)
        .onScrollGeometryChange(for: CGFloat.self) { $0.containerSize.height } action: { _, height in visibleHeight = height + tunerReserve }  // the card's full height: the container excludes the margin kept for the handle
        .onScrollGeometryChange(for: CGFloat.self) { $0.containerSize.width } action: { _, width in containerWidth = width }
        .overlay(alignment: .bottom) { TunerDrawer(expanded: $tunerOpen).padding(.bottom, 8) }
        .refreshable { await radio.refresh() }
        .detailSheet($detail)
    }

    /// A line of the song's text that opens `route`; plain text when the song has no id to open.
    @ViewBuilder private func detailLink<Label: View>(_ route: DetailRoute?, id: String, @ViewBuilder label: () -> Label) -> some View {
        if let route {
            Button { detail = route } label: { label() }
                .buttonStyle(.plain)
                .accessibilityHint("Opens the details")
                .accessibilityIdentifier(id)
        } else { label() }
    }
}

private struct StationHeader: View {
    @Environment(VibeAppModel.self) private var model
    @State private var showingStation = false

    var body: some View {
        let station = model.radio.currentStation
        HStack {
            Button { showingStation = station != nil } label: {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 4) { Text(station?.name ?? "Radio").font(.headline); if station != nil { Image(systemName: "chevron.right").font(.caption2) } }
                    if let station { Text("FM \(station.frequencyLabel)").font(.caption.monospaced()).foregroundStyle(.secondary) }
                }.foregroundStyle(.primary)
            }.buttonStyle(.plain).accessibilityHint("Shows what this station is made of")
            Spacer()
            if let pending = model.radio.pendingStation, pending.id != station?.id {
                Button("Switch to \(pending.name)") { Task { await model.radio.switchNow() } }
                    .buttonStyle(.bordered).controlSize(.small)
            }
        }
        .sheet(isPresented: $showingStation) { if let id = station?.id { StationSheet(stationID: id) } }
    }
}

/// The sleeve with the record sliding out behind it. Long-press the sleeve for
/// "start radio from this song" and links into the Library.
struct SleeveAndRecord: View {
    @Environment(VibeAppModel.self) private var model
    let track: Radio.Track?
    var side: CGFloat = RadioLayout.maxSleeve
    /// How far the record slides out; its label must stay mostly clear of the sleeve to be grabbable.
    private var discOffset: CGFloat { RadioLayout.discOffset(side: side) }

    var body: some View {
        ZStack(alignment: .leading) {
            VinylDisc(track: track, size: side, outOffset: discOffset)
            AsyncImage(url: track?.artworkURL) { $0.resizable().scaledToFill() } placeholder: {
                ZStack { Color(.secondarySystemBackground); Image(systemName: "music.note").font(.system(size: 44)).foregroundStyle(.secondary) }
            }
            .frame(width: side, height: side)
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
            .shadow(color: .black.opacity(0.3), radius: 16, y: 8)
            .contextMenu {
                if let track {
                    Button("Start radio from this song", systemImage: "dot.radiowaves.left.and.right") { Task { await model.radio.startRadioFromCurrentTrack() } }
                    if let albumID = track.albumId {
                        Button("Open the album", systemImage: "square.stack") { open(.album, albumID, track.album ?? track.title) }
                    }
                    if let artistID = track.artistId {
                        Button("Open the artist", systemImage: "person") { open(.artist, artistID, track.artist) }
                    }
                }
            }
            .accessibilityLabel(track.map { "\($0.title) by \($0.artist)" } ?? "No song playing")
        }
        .frame(width: side + discOffset, height: side, alignment: .leading)
        .frame(maxWidth: .infinity)
        // The sleeve row is wider than the card's text column so the record can be large.
        .padding(.horizontal, -(20 - RadioLayout.rowMargin))
    }

    private func open(_ kind: Radio.SeedKind, _ id: String, _ title: String) {
        model.coordinator.focusInLibrary(.init(kind: kind, spotifyId: id, title: title))
        model.tab = .library
    }
}

private struct ProgressScrubber: View {
    @Environment(VibeAppModel.self) private var model
    @State private var scrubbing: Double?

    var body: some View {
        let radio = model.radio
        TimelineView(.periodic(from: .now, by: 0.5)) { context in
            let duration = max(radio.duration, 1)
            let position = scrubbing ?? radio.position(at: context.date)
            VStack(spacing: 4) {
                Slider(value: Binding(get: { min(position, duration) }, set: { scrubbing = $0 }), in: 0...duration) { editing in
                    if !editing, let target = scrubbing { scrubbing = nil; Task { await radio.seek(to: target) } }
                }
                .disabled(radio.track == nil)
                HStack {
                    Text(Self.format(position)); Spacer(); Text(Self.format(radio.duration))
                }.font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
            }
        }
    }

    static func format(_ seconds: TimeInterval) -> String {
        let total = Int(max(0, seconds)); return String(format: "%d:%02d", total / 60, total % 60)
    }
}

private struct Transport: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var lyricsSoon = false

    var body: some View {
        let radio = model.radio
        // The three transport buttons are centred in the card; the "more" menu sits at the leading edge
        // and cannot pull them off-centre. At accessibility sizes there is no room beside the buttons,
        // so the menu goes on a row of its own below them.
        Group {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(spacing: 8) { controls(radio); moreMenu(radio) }.frame(maxWidth: .infinity)
            } else {
                CenteredControlsRow { moreMenu(radio) } center: { controls(radio) }
            }
        }
        .foregroundStyle(model.atmosphere.primary)
        .disabled(radio.isBusy)
        .alert("Lyrics are coming soon", isPresented: $lyricsSoon) { Button("OK", role: .cancel) {} } message: { Text("Juke will show lyrics once a licensed provider is chosen.") }
    }

    private func moreMenu(_ radio: RadioController) -> some View {
        Menu {
            Button("Save this moment", systemImage: "bookmark") { Task { await radio.saveMoment() } }
            Button("Put the record away", systemImage: "tray.and.arrow.down") { Task { await radio.putAway() } }
            Button("Lyrics", systemImage: "text.quote") { lyricsSoon = true }
        } label: { Image(systemName: "ellipsis.circle").font(.title2).frame(minWidth: 44, minHeight: 44) }
            .accessibilityIdentifier("radio.more")
    }

    private func controls(_ radio: RadioController) -> some View {
        HStack(spacing: 26) {
            Button { Task { await radio.previous() } } label: { Image(systemName: "backward.fill").font(.title2).frame(minWidth: 44, minHeight: 44) }
                .accessibilityLabel("Previous song")
                .accessibilityIdentifier("radio.previous")
            Button { Task { await radio.togglePlayPause() } } label: {
                Image(systemName: radio.isPlaying ? "pause.circle.fill" : "play.circle.fill").font(.system(size: 64))
            }
            .accessibilityLabel(radio.isPlaying ? "Pause" : "Play")
            .accessibilityIdentifier("radio.playPause")
            Button { Task { await radio.skip() } } label: { Image(systemName: "forward.fill").font(.title2).frame(minWidth: 44, minHeight: 44) }
                .accessibilityLabel("Next song")
                .accessibilityIdentifier("radio.next")
                .contextMenu {
                    Button("Not on this station", systemImage: "minus.circle") { Task { await radio.keepOut(.notOnStation) } }
                    Button("Less of this artist", systemImage: "person.crop.circle.badge.minus") { Task { await radio.keepOut(.lessArtist) } }
                    Button("Never this artist", systemImage: "nosign") { Task { await radio.keepOut(.neverArtist) } }
                }
        }
    }
}

private struct ReactionEmojiSlider: View {
    @Environment(VibeAppModel.self) private var model
    @State private var words = ""
    @State private var addingWords = false
    @State private var previewEmoji: String?
    @State private var isScrubbing = false
    @State private var isTouchActive = false
    @State private var didScrub = false
    @State private var lastDragLocation: CGPoint?
    @State private var holdTask: Task<Void, Never>?

    var body: some View {
        let radio = model.radio
        VStack(spacing: 10) {
            GeometryReader { geometry in
                let reactions = Array(radio.sliderEmojiReactions.prefix(7))
                VStack(spacing: 0) {
                    if isScrubbing, let previewEmoji {
                        Text(previewEmoji)
                            .font(.system(size: 44))
                            .frame(height: 48)
                            .transition(.scale.combined(with: .opacity))
                    }
                    HStack(spacing: 2) {
                        ForEach(reactions, id: \.self) { reaction in
                            let selected = radio.currentReactions.contains(reaction)
                            Button {
                                Task { await radio.toggleReaction(reaction) }
                            } label: {
                                Text(reaction)
                                    .font(.system(size: 28))
                                    .frame(maxWidth: .infinity)
                                    .frame(height: 48)
                                    .background(selected ? model.atmosphere.primary.opacity(0.2) : .clear, in: Capsule())
                                    .contentShape(Capsule())
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel("React with \(reaction)")
                            .accessibilityValue(selected ? "Selected" : "Not selected")
                            .accessibilityHint("Double-tap to add or remove this feeling. Or touch and hold, then slide to preview.")
                        }
                    }
                    .contentShape(Rectangle())
                    .highPriorityGesture(touchGesture(reactions: reactions, width: geometry.size.width, radio: radio))
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier("radio.emojiSlider")
                    .accessibilityLabel("Reaction slider")
                    .accessibilityValue(radio.currentReactions.first(where: reactions.contains) ?? "No feeling selected")
                    .accessibilityHint("Swipe up or down to choose the previous or next feeling. Double-tap an emoji to add or remove it.")
                    .accessibilityAdjustableAction { direction in
                        let current = radio.currentReactions.first(where: reactions.contains)
                        let step = direction == .increment ? 1 : -1
                        if let adjacent = ReactionEmojiSliderLogic.adjacent(to: current, direction: step, in: reactions) {
                            Task { await radio.chooseReaction(adjacent) }
                        }
                    }
                    .disabled(radio.track == nil)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .frame(height: isScrubbing ? 96 : 48)
            .animation(.snappy(duration: 0.18), value: isScrubbing)
            let wordReactions = radio.currentReactions.filter { !RadioController.isEmoji($0) }
            if !wordReactions.isEmpty {
                HStack(spacing: 8) {
                    ForEach(wordReactions, id: \.self) { reaction in
                        Button { Task { await radio.toggleReaction(reaction) } } label: {
                            Text(reaction)
                                .font(.subheadline)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 7)
                                .background(model.atmosphere.primary.opacity(0.16), in: Capsule())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Remove reaction \(reaction)")
                        .accessibilityValue("Selected")
                    }
                }
                .accessibilityIdentifier("radio.wordReactions")
            }
            Button { addingWords = true } label: {
                Label("Add your own reaction", systemImage: "plus")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("radio.addReaction")
            .disabled(radio.track == nil)
            if let suggestion = radio.suggestion {
                HStack {
                    Text("Sounds like \(suggestion.name)").font(.footnote)
                    Button("Tune") { Task { await radio.acceptSuggestion() } }.buttonStyle(.bordered).controlSize(.small)
                    Button("Not now") { radio.dismissSuggestion() }.controlSize(.small)
                }
            }
        }
        .alert("How does it feel?", isPresented: $addingWords) {
            TextField("A few words", text: $words)
            Button("Add") { let text = words; words = ""; Task { await radio.addWords(text) } }
            Button("Cancel", role: .cancel) { words = "" }
        }
    }

    private func touchGesture(reactions: [String], width: CGFloat, radio: RadioController) -> some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .local)
            .onChanged { drag in
                lastDragLocation = drag.location
                if !isTouchActive {
                    isTouchActive = true
                    didScrub = false
                    holdTask = Task { @MainActor in
                        do {
                            try await Task.sleep(nanoseconds: 280_000_000)
                        } catch {
                            return
                        }
                        guard isTouchActive, !reactions.isEmpty else { return }
                        didScrub = true
                        isScrubbing = true
                        updatePreview(at: lastDragLocation, reactions: reactions, width: width)
                    }
                } else if didScrub {
                    updatePreview(at: drag.location, reactions: reactions, width: width)
                }
            }
            .onEnded { drag in
                holdTask?.cancel()
                holdTask = nil
                isTouchActive = false
                defer {
                    didScrub = false
                    isScrubbing = false
                    previewEmoji = nil
                    lastDragLocation = nil
                }
                guard !reactions.isEmpty else { return }
                let location = drag.location
                let index = ReactionEmojiSliderLogic.slot(at: location.x, width: width, count: reactions.count, spacing: 2)
                let reaction = reactions[index]
                if didScrub {
                    Task { await radio.chooseReaction(reaction) }
                } else {
                    Task { await radio.toggleReaction(reaction) }
                }
            }
    }

    private func updatePreview(at location: CGPoint?, reactions: [String], width: CGFloat) {
        guard let location, !reactions.isEmpty else { return }
        let index = ReactionEmojiSliderLogic.slot(at: location.x, width: width, count: reactions.count, spacing: 2)
        previewEmoji = reactions[index]
    }
}

/// A calm connection or playback error that floats over Radio without shifting
/// its scroll content. The close button leaves recovery actions available until
/// the listener dismisses it.
struct ConnectionIssueOverlay: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.openURL) private var openURL
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let issue: RadioIssue
    /// "Tried 3 times" after repeated failed presses.
    var triesCaption: String?
    /// Changes on every failed press; the banner answers each one.
    var nudge = 0
    let onDismiss: () -> Void
    @State private var nudged = false

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 8) {
                Text(issue.message).font(.callout).fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("radio.issueMessage")
                if let triesCaption {
                    Text(triesCaption).font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("radio.issueTries")
                }
                switch issue.nextOutcome {
                case .retry, .offline:
                    Button("Try again") { Task { await model.radio.skip() } }
                        .buttonStyle(.bordered).disabled(model.radio.isBusy).accessibilityIdentifier("radio.tryAgain")
                case .exhausted:
                    Button("New station") { model.coordinator.openNewStation(JukeCoordinator.NewStationDraft()) }
                        .buttonStyle(.bordered).accessibilityIdentifier("radio.issueNewStation")
                case nil: EmptyView()
                }
                switch issue {
                case .noActiveDevice:
                    // Only Spotify can wake a player iOS has suspended. Radio resumes when Juke is active again.
                    Button("Open Spotify") {
                        model.radio.willOpenSpotify()
                        if let url = URL(string: "spotify://") { openURL(url) }
                    }
                    .buttonStyle(.bordered).accessibilityIdentifier("radio.openSpotify")
                case .spotifyNotLinked:
                    Button("Connect Spotify") { openURL(AppConfiguration.currentFrontendURL) }.buttonStyle(.bordered)
                default: EmptyView()
            }
            }
            Spacer(minLength: 0)
            Button(action: onDismiss) {
                Image(systemName: "xmark")
                    .font(.caption.weight(.bold))
                    .frame(width: 44, height: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Dismiss")
            .accessibilityIdentifier("radio.dismissIssue")
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).strokeBorder(nudged ? AnyShapeStyle(model.atmosphere.primary) : AnyShapeStyle(.primary.opacity(0.1)), lineWidth: nudged ? 2 : 1))
        .shadow(color: .black.opacity(0.12), radius: 14, y: 6)
        .scaleEffect(nudged && !reduceMotion ? 1.03 : 1)
        // A banner that is already up answers another failed press with a short pulse (border only with Reduce Motion).
        .task(id: nudge) {
            guard nudge > 0 else { return }
            withAnimation(.easeOut(duration: 0.12)) { nudged = true }
            try? await Task.sleep(for: .milliseconds(450))
            withAnimation(.easeOut(duration: 0.3)) { nudged = false }
        }
    }
}

/// Previous, play/pause and next for whatever is playing. Disabled (but visible)
/// when the sound comes from a source Juke cannot control.
struct PlayerControlButtons: View {
    @Environment(VibeAppModel.self) private var model

    var body: some View {
        let transport = model.transport
        HStack(spacing: 0) {
            control("backward.fill", "Previous song", id: "player.previous") { await transport.press(.previous) }
            control(transport.isPlaying ? "pause.fill" : "play.fill", transport.isPlaying ? "Pause" : "Play", id: "player.playPause") { await transport.press(.playPause) }
            control("forward.fill", "Next song", id: "player.next") { await transport.press(.next) }
        }
        .disabled(!transport.isControllable)
        .onChange(of: model.nowPlaying.isPlaying) { _, _ in transport.observed() }
        .alert("Playback", isPresented: Binding(get: { transport.message != nil }, set: { if !$0 { transport.message = nil } })) {
            Button("OK", role: .cancel) {}
        } message: { Text(transport.message ?? "") }
    }

    private func control(_ symbol: String, _ label: String, id: String, action: @escaping () async -> Void) -> some View {
        Button { Task { await action() } } label: { Image(systemName: symbol).font(.title3) }
            .buttonStyle(.plain)
            .frame(width: 36, height: 44)
            .contentShape(Rectangle())
            .accessibilityLabel(label)
            .accessibilityIdentifier(id)
    }
}

/// Persistent player shown above the tab bar on every tab except Radio (which has
/// its own) and inside Chat's composer (`embedded`).
/// Always offers previous, play/pause and next, whatever is playing.
struct MiniPlayerPill: View {
    @Environment(VibeAppModel.self) private var model
    var embedded = false
    /// Why the last press did nothing; shown for a few seconds in place of the artist.
    @State private var failure: String?
    @State private var pulse = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let radio = model.radio
        // The controls stay in the middle of the island; what is playing gives way on the left.
        CenteredControlsRow {
            HStack(spacing: 8) {
                if radio.isOnAir, let track = radio.track {
                    MiniPlayerArtwork(url: track.artworkURL, local: nil, tint: model.atmosphere.primary)
                    // A paused song stays here with its controls; the line says why nothing is playing.
                    titles(track.title, failure ?? radio.status.caption ?? track.artist, warning: failure != nil)
                } else {
                    MiniPlayerArtwork(url: model.nowPlaying.track?.artworkURL, local: model.nowPlaying.track?.localArtwork, tint: model.atmosphere.primary)
                    titles(model.nowPlaying.track?.title ?? "Listening for music",
                           model.nowPlaying.track.map { "\($0.artist) · \($0.source)" } ?? model.nowPlaying.status)
                }
            }
        } center: {
            PlayerControlButtons()
        } trailing: {
            if !radio.isOnAir {
                Menu {
                    Button(model.nowPlaying.isListeningAroundMe ? "Stop Around Me" : "Identify Around Me") { Task { await model.nowPlaying.setAroundMe(!model.nowPlaying.isListeningAroundMe) } }
                    Text("Apple Music and connected Spotify playback are checked automatically while Juke is active.")
                } label: { Image(systemName: "ellipsis.circle").font(.title3).frame(width: 30, height: 44) }
            } else {
                Color.clear.frame(width: 1, height: 1)
            }
        }
        .padding(.horizontal, 10).padding(.vertical, 8)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: MiniPlayerStyle.cornerRadius))
        .overlay(RoundedRectangle(cornerRadius: MiniPlayerStyle.cornerRadius).strokeBorder(.primary.opacity(MiniPlayerStyle.borderOpacity), lineWidth: MiniPlayerStyle.borderWidth))
        .shadow(color: .black.opacity(MiniPlayerStyle.shadowOpacity), radius: MiniPlayerStyle.shadowRadius, y: 4)
        .padding(.horizontal, embedded ? 0 : 16).padding(.top, embedded ? 2 : 6).padding(.bottom, embedded ? 6 : 8)
        .contentShape(Rectangle())
        .onTapGesture { if radio.isOnAir { model.tab = .radio } }
        .background { Color.clear.accessibilityIdentifier("player.island") }
        // Away from Radio there is no banner: each failed press says why here, then the artist returns.
        .task(id: radio.failedPresses) {
            guard radio.failedPresses > 0, let label = radio.issue?.shortLabel else { failure = nil; return }
            failure = label
            // The same answer twice still has to look like an answer: the line pulses on every press.
            withAnimation(.easeOut(duration: 0.12)) { pulse = true }
            try? await Task.sleep(for: .milliseconds(450))
            withAnimation(.easeOut(duration: 0.3)) { pulse = false }
            try? await Task.sleep(for: .seconds(MiniPlayerStyle.failureSeconds))
            if !Task.isCancelled { failure = nil }
        }
    }

    private func titles(_ title: String, _ subtitle: String, warning: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.subheadline.bold()).lineLimit(1)
            Text(subtitle).font(.caption.weight(warning ? .semibold : .regular))
                .foregroundStyle(warning ? HierarchicalShapeStyle.primary : .secondary).lineLimit(1)
                .scaleEffect(pulse && !reduceMotion ? 1.06 : 1, anchor: .leading)
                .opacity(pulse && reduceMotion ? 0.45 : 1)
                .accessibilityIdentifier("miniPlayer.status")
        }
    }
}

/// Island styling, kept in one place so the separation from page content is testable.
enum MiniPlayerStyle {
    static let cornerRadius: CGFloat = 20
    static let borderWidth: CGFloat = 1
    static let borderOpacity: Double = 0.22
    static let shadowOpacity: Double = 0.22
    static let shadowRadius: CGFloat = 12
    /// How long the compact player says why a press failed.
    static let failureSeconds: Double = 5
}

private struct MiniPlayerArtwork: View {
    let url: URL?
    let local: UIImage?
    let tint: Color

    var body: some View {
        Group {
            if let local { Image(uiImage: local).resizable().scaledToFill() }
            else if let url { AsyncImage(url: url) { $0.resizable().scaledToFill() } placeholder: { Color.secondary.opacity(0.15) } }
            else { tint.opacity(0.2).overlay(Image(systemName: "waveform")) }
        }
        .frame(width: 42, height: 42).clipShape(RoundedRectangle(cornerRadius: 8))
    }
}
