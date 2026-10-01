import SwiftUI

/// Radio section: the record card, or New Station when the coordinator
/// routes there, or the one-time "Tune in" card on first run.
struct RadioScreen: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ZStack {
            switch model.coordinator.radioRoute {
            case .nowPlaying:
                Group {
                    if !model.radio.hasTunedIn, !model.radio.isOnAir, model.detection.track == nil {
                        TuneInCard()
                    } else {
                        RadioCard()
                    }
                }
                .transition(stageTransition)
            case .newStation(let draft):
                NewStationScreen(draft: draft)
                    .transition(stageTransition)
            }
        }
        .animation(JukeMotion.navigationIn(reduceMotion: reduceMotion), value: model.coordinator.radioRoute)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("radio.screen")
    }

    private var stageTransition: AnyTransition {
        reduceMotion ? .opacity : .asymmetric(
            insertion: .opacity.combined(with: .offset(y: JukeMotion.Stage.inOffset)).combined(with: .scale(scale: JukeMotion.Stage.inScale)),
            removal: .opacity.combined(with: .offset(y: JukeMotion.Stage.outOffset))
        )
    }
}

/// First run: one tap starts My Station.
private struct TuneInCard: View {
    @Environment(AppModel.self) private var model
    @Environment(\.jukeTheme) private var theme

    var body: some View {
        let radio = model.radio
        JukeCard(padding: EdgeInsets(top: 40, leading: 48, bottom: 36, trailing: 48)) {
            VStack(spacing: 22) {
                VinylDisc(label: theme.accent.color, size: 132, isSpinning: radio.isBusy)
                VStack(spacing: 8) {
                    Text("Juke Radio")
                        .font(JukeFont.display(34, weight: .bold))
                        .tracking(-0.8)
                    Text("My Station plays music picked for you and keeps learning as you listen. It never stops between songs.")
                        .font(JukeFont.body(16))
                        .foregroundStyle(theme.sub.color)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 420)
                }
                Button {
                    Task { await radio.tuneIn() }
                } label: {
                    Label(radio.isBusy ? "Tuning in…" : "Tune in", systemImage: "play.fill")
                        .font(JukeFont.body(17, weight: .bold))
                        .padding(.horizontal, 10)
                        .frame(minHeight: 52)
                }
                .buttonStyle(JukeAccentButtonStyle())
                .keyboardShortcut(.defaultAction)
                .disabled(radio.isBusy)
                .accessibilityIdentifier("radio.tuneIn")
                if let issue = radio.issue {
                    RadioIssueView(issue: issue)
                }
            }
            .frame(width: JukeMetrics.radioCardWidth - 96)
        }
    }
}

/// Which player the card reflects: Juke radio, or whatever Apple Music or
/// Spotify is playing outside radio (simplified local controls).
enum RadioCardSource { case radio, local, idle }

/// The radio card (reference: the "Now playing" section).
struct RadioCard: View {
    @Environment(AppModel.self) private var model
    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    enum Panel: Equatable { case station, lyrics }
    enum ReactionPopover: Equatable { case picker, words }

    @State private var sleeveOpen = false
    @State private var seekDelta: TimeInterval?
    @State private var panel: Panel?
    @State private var popover: ReactionPopover?
    @State private var skipMenuOpen = false
    @State private var wordsDraft = ""
    @State private var dialActivity = DialActivity()

    private var radio: RadioController { model.radio }

    private var source: RadioCardSource {
        if radio.isOnAir || radio.isPutAway { return .radio }
        if model.detection.track != nil { return .local }
        return .idle
    }

    var body: some View {
        JukeCard(padding: EdgeInsets()) {
            VStack(alignment: .leading, spacing: 12) {
                RadioHero(model: heroModel, sleeveOpen: $sleeveOpen, seekDelta: $seekDelta, sleeveOptions: sleeveOptions)
                titleBlock
                reactionStrip
                progress
                controls
                FMDialView(
                    stations: radio.stations,
                    tunedFrequency: radio.tunedStation?.frequency ?? FMDial.lowest,
                    currentStationID: radio.currentStationID,
                    tunedStationID: radio.tunedStation?.id,
                    showsCue: !radio.isPutAway && radio.pendingStationID != nil,
                    onTune: { radio.tune(to: $0) },
                    onNewStation: { model.coordinator.openNewStation() },
                    onSwitchNow: { Task { await radio.switchNow() } },
                    onMove: { id, frequency in await radio.moveStation(id, to: frequency) },
                    activity: $dialActivity
                )
                RadioStatusLine(activity: dialActivity, source: source)
            }
            .padding(EdgeInsets(top: 22, leading: 32, bottom: 14, trailing: 32))
            .overlay { panelOverlay }
        }
        .frame(width: JukeMetrics.radioCardWidth)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("radio.card")
        .onChange(of: radio.track?.spotifyId) { _, _ in
            sleeveOpen = false
            skipMenuOpen = false
        }
    }

    // MARK: Hero

    private var heroModel: RadioHeroModel {
        let detection = model.detection
        let radio = radio
        switch source {
        case .radio, .idle:
            return RadioHeroModel(
                artworkURL: radio.track?.artworkURL,
                albumName: radio.track?.album ?? radio.track?.artist ?? "Juke Radio",
                title: radio.track?.title ?? "Juke Radio",
                isPlaying: radio.isPlaying,
                isPutAway: radio.isPutAway,
                canSeek: radio.isOnAir && radio.track != nil,
                position: { radio.position(at: $0) },
                duration: radio.duration,
                togglePlay: { Task { await radio.togglePlayPause() } },
                spin: { degrees in Task { await radio.spin(degrees: degrees) } },
                putAway: { Task { await radio.putAway() } },
                comeBack: { Task { await radio.comeBack() } }
            )
        case .local:
            return RadioHeroModel(
                artworkURL: detection.track?.artworkURL,
                albumName: detection.track?.album ?? detection.track?.artist ?? "",
                title: detection.track?.title ?? "",
                isPlaying: detection.isPlaying,
                isPutAway: false,
                canSeek: detection.canControlPlayback && detection.playbackDuration > 0,
                position: { detection.estimatedPlaybackPosition(at: $0) },
                duration: detection.playbackDuration,
                togglePlay: { Task { await detection.togglePlayback() } },
                spin: { degrees in
                    let target = detection.estimatedPlaybackPosition() + VinylSeek.seconds(forDegrees: degrees)
                    Task { await detection.seek(to: max(0, target)) }
                },
                putAway: { if detection.isPlaying { Task { await detection.togglePlayback() } } },
                comeBack: { if !detection.isPlaying { Task { await detection.togglePlayback() } } }
            )
        }
    }

    private var sleeveOptions: [RadioHero.SleeveOption] {
        let isRadio = source == .radio
        let title = isRadio ? radio.track?.title ?? "" : model.detection.track?.title ?? ""
        let artist = isRadio ? radio.track?.artist ?? "" : model.detection.track?.artist ?? ""
        let album = isRadio ? radio.track?.album : model.detection.track?.album
        let albumID = isRadio ? radio.track?.albumId : nil
        let artistID = isRadio ? radio.track?.artistId : nil
        var options = [
            RadioHero.SleeveOption(id: "lyrics", label: "Lyrics", sub: "Follows the song as it plays") { panel = .lyrics },
            RadioHero.SleeveOption(id: "album", label: albumID?.isEmpty == false ? "Open the album" : "Find the album",
                                   sub: album ?? "In the crate") {
                openInLibrary(kind: .album, id: albumID, title: album ?? title)
            },
            RadioHero.SleeveOption(id: "artist", label: "Open the artist", sub: artist.isEmpty ? "In the crate" : artist) {
                openInLibrary(kind: .artist, id: artistID, title: artist)
            },
        ]
        if isRadio, radio.track != nil {
            options.append(RadioHero.SleeveOption(id: "startRadio", label: "Start radio from this song", sub: "Tunes in next") {
                Task { await radio.startRadioFromCurrentTrack() }
            })
        }
        return options
    }

    private func openInLibrary(kind: Radio.SeedKind, id: String?, title: String) {
        model.coordinator.focusInLibrary(.init(kind: kind, spotifyId: id ?? "", title: title))
        model.section = .library
    }

    // MARK: Title

    private var titleBlock: some View {
        VStack(alignment: .leading, spacing: 2) {
            Button { panel = .station } label: {
                HStack(spacing: 6) {
                    Text(eyebrow)
                        .font(JukeFont.body(12, weight: .bold))
                        .tracking(1.6)
                        .lineLimit(1)
                    Image(systemName: "chevron.down").font(.system(size: 11, weight: .bold))
                }
                .foregroundStyle(theme.ink.color)
                .frame(minHeight: 28)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(radio.currentStation == nil)
            .accessibilityLabel("\(radio.currentStation?.name ?? "Station") settings: seeds, feelings and what to keep out")
            .accessibilityIdentifier("radio.stationButton")
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(JukeFont.display(28, weight: .bold))
                    .tracking(-0.6)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier("radio.title")
                Text(subtitle)
                    .font(JukeFont.body(16))
                    .foregroundStyle(theme.sub.color)
                    .lineLimit(1)
            }
            .id(title)
            .transition(reduceMotion ? .identity : .opacity.combined(with: .offset(y: 8)))
            .animation(reduceMotion ? nil : JukeMotion.easeOutSoft(0.6), value: title)
        }
    }

    private var eyebrow: String {
        let name = (radio.currentStation?.name ?? "Juke Radio").uppercased()
        switch source {
        case .local: return "\((model.detection.providerName ?? "Now playing").uppercased()) · \(name) IS OFF AIR"
        case .radio, .idle:
            if radio.isPutAway { return "PUT AWAY · \(name)" }
            return radio.isOnAir ? "ON AIR · \(name)" : "OFF AIR · \(name)"
        }
    }

    private var title: String {
        switch source {
        case .local: model.detection.track?.title ?? ""
        case .radio: radio.track?.title ?? "Juke Radio"
        case .idle: "The radio is off"
        }
    }

    private var subtitle: String {
        switch source {
        case .local:
            let track = model.detection.track
            return [track?.artist, track?.album].compactMap { $0 }.joined(separator: " · ")
        case .radio:
            return radio.track?.artist ?? ""
        case .idle:
            return "Press play to tune in to \(radio.tunedStation?.name ?? "My Station")."
        }
    }

    // MARK: Reactions

    private var reactionStrip: some View {
        HStack(spacing: 6) {
            if source == .radio, radio.track != nil {
                ForEach(radio.stripReactions, id: \.self) { reaction in
                    ReactionChip(reaction: reaction, isOn: radio.currentReactions.contains(reaction)) {
                        Task { await radio.toggleReaction(reaction) }
                    }
                }
                HoldableButton(holdName: "Describe it in words") {
                    popover = popover == .picker ? nil : .picker
                    skipMenuOpen = false
                } onHold: {
                    popover = .words
                    skipMenuOpen = false
                } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(theme.sub.color)
                        .frame(width: 36, height: 36)
                        .overlay(Circle().strokeBorder(popover != nil ? theme.accent.color : theme.line,
                                                       style: StrokeStyle(lineWidth: 1.5, dash: [4, 3])))
                        .contentShape(Circle())
                }
                .help("Click: emoji. Hold: in your words.")
                .accessibilityLabel("Add a reaction. Hold to describe it in words.")
                .accessibilityIdentifier("radio.reactions.add")
                .contextMenu {
                    Button("Pick an emoji…") { popover = .picker }
                    Button("Describe it in words…") { popover = .words }
                }
                .popover(isPresented: popoverBinding(.picker), arrowEdge: .bottom) { emojiPicker }
                .background {
                    Color.clear.popover(isPresented: popoverBinding(.words), arrowEdge: .bottom) { wordsField }
                }
            }
            Spacer(minLength: 8)
            Text(source == .radio && radio.track != nil ? (radio.currentReactions.isEmpty ? "How does it feel?" : "Steers what plays next") : "")
                .font(JukeFont.body(12))
                .foregroundStyle(theme.sub.color)
        }
        .frame(minHeight: 38)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("How does this song feel? Pick any.")
    }

    private func popoverBinding(_ kind: ReactionPopover) -> Binding<Bool> {
        Binding(get: { popover == kind }, set: { if !$0, popover == kind { popover = nil } })
    }

    private var emojiPicker: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("How does it feel? Pick any.").font(JukeFont.body(13, weight: .bold))
                Spacer()
                Button("Done") { popover = nil }.buttonStyle(.plain).font(JukeFont.body(13, weight: .semibold))
            }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 4), count: 8), spacing: 4) {
                ForEach(radio.pickerReactions, id: \.self) { emoji in
                    let on = radio.currentReactions.contains(emoji)
                    Button { Task { await radio.toggleReaction(emoji) } } label: {
                        Text(emoji)
                            .font(.system(size: 19))
                            .frame(maxWidth: .infinity, minHeight: 40)
                            .background(on ? theme.accentSoft.color : .clear, in: RoundedRectangle(cornerRadius: 10))
                            .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(on ? theme.accent.color : theme.line, lineWidth: 1.5))
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(on ? "Remove \(emoji)" : "Feels \(emoji)")
                }
            }
            Text("Want words instead? Press and hold the + button.")
                .font(JukeFont.body(12))
                .foregroundStyle(theme.sub.color)
        }
        .padding(14)
        .frame(width: 380)
        .foregroundStyle(theme.ink.color)
        .background(theme.card.color)
        .accessibilityIdentifier("radio.emojiPicker")
    }

    private var wordsField: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("In your words, how does this song feel?").font(JukeFont.body(13, weight: .bold))
            HStack(spacing: 6) {
                TextField("first cold morning of fall", text: $wordsDraft)
                    .textFieldStyle(.plain)
                    .font(JukeFont.body(15))
                    .padding(.horizontal, 14)
                    .frame(height: 44)
                    .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(theme.accent.color, lineWidth: 1.5))
                    .onChange(of: wordsDraft) { _, value in
                        let limit = Radio.ReactionsRequest.maxPhraseLength
                        if value.count > limit { wordsDraft = String(value.prefix(limit)) }
                    }
                    .onSubmit(saveWords)
                    .accessibilityLabel("In your words")
                    .accessibilityIdentifier("radio.words.field")
                Button("Save", action: saveWords)
                    .buttonStyle(JukeAccentButtonStyle())
                    .disabled(RadioController.normalizedWords(wordsDraft).isEmpty)
            }
            Text("Saved like any emoji. Juke reads it to steer this station.")
                .font(JukeFont.body(12))
                .foregroundStyle(theme.sub.color)
        }
        .padding(14)
        .frame(width: 420)
        .foregroundStyle(theme.ink.color)
        .background(theme.card.color)
    }

    private func saveWords() {
        let words = wordsDraft
        wordsDraft = ""
        popover = nil
        Task { await radio.addWords(words) }
    }

    // MARK: Progress

    private var progress: some View {
        let hero = heroModel
        return TimelineView(.periodic(from: .now, by: 0.5)) { context in
            let duration = hero.duration
            let position = hero.position(context.date)
            let shown = seekDelta.map { VinylSeek.previewTarget(position: position, duration: duration, delta: $0) } ?? position
            let fraction = duration > 0 ? min(1, max(0, shown / duration)) : 0
            VStack(spacing: 5) {
                GeometryReader { proxy in
                    ZStack(alignment: .leading) {
                        Capsule().fill(theme.well.color)
                        Capsule().fill(theme.ink.color).frame(width: proxy.size.width * fraction)
                    }
                }
                .frame(height: 4)
                HStack {
                    Text(RadioGesture.clock(shown))
                    Spacer()
                    Text(duration > 0 ? RadioGesture.clock(duration) : "–:––")
                }
                .font(JukeFont.body(12))
                .monospacedDigit()
                .foregroundStyle(theme.sub.color)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Playback position")
            .accessibilityValue("\(RadioGesture.clock(shown)) of \(RadioGesture.clock(duration))")
            .accessibilityAdjustableAction { direction in
                guard hero.canSeek else { return }
                hero.spin(VinylSeek.degrees(forSeconds: direction == .increment ? 15 : -15))
            }
            .accessibilityIdentifier("radio.progress")
        }
    }

    // MARK: Controls

    private var controls: some View {
        let hero = heroModel
        return HStack(spacing: 18) {
            Color.clear.frame(width: 44, height: 44)
            Button { hero.isPutAway ? hero.comeBack() : hero.togglePlay() } label: {
                RadioIconLabel(systemName: hero.isPlaying ? "pause.fill" : "play.fill", size: 60, iconSize: 22, style: .accent)
            }
            .buttonStyle(.plain)
            .disabled(source == .local && !model.detection.canControlPlayback)
            .accessibilityLabel(hero.isPlaying ? "Pause" : "Play")
            .accessibilityIdentifier("radio.playPause")
            skipButton
            Button {
                Task { await saveMoment() }
            } label: {
                RadioIconLabel(systemName: "bookmark", size: 44, iconSize: 19, style: .plain)
            }
            .buttonStyle(.plain)
            .disabled(source == .idle)
            .help("Save to Memories")
            .accessibilityLabel("Save this moment to Memories")
            .accessibilityIdentifier("radio.save")
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private var skipButton: some View {
        if source == .local {
            Button { Task { await model.detection.nextTrack() } } label: {
                RadioIconLabel(systemName: "forward.end.fill", size: 44, iconSize: 18, style: .well)
            }
            .buttonStyle(.plain)
            .disabled(!model.detection.canControlPlayback)
            .accessibilityLabel("Next track")
            .accessibilityIdentifier("radio.skip")
        } else {
            HoldableButton(holdName: "Keep this out") {
                Task { await radio.skip() }
            } onHold: {
                skipMenuOpen = true
                popover = nil
            } label: {
                RadioIconLabel(systemName: "forward.end.fill", size: 44, iconSize: 18, style: .well)
            }
            .disabled(!radio.isOnAir)
            .help("Click: skip. Hold: keep this out.")
            .accessibilityLabel("Skip. Hold for station options.")
            .accessibilityIdentifier("radio.skip")
            .contextMenu { keepOutButtons(menu: true) }
            .popover(isPresented: $skipMenuOpen, arrowEdge: .bottom) {
                VStack(alignment: .leading, spacing: 0) { keepOutButtons(menu: false) }
                    .padding(6)
                    .frame(width: 264)
                    .foregroundStyle(theme.ink.color)
                    .background(theme.card.color)
                    .accessibilityIdentifier("radio.skipMenu")
            }
        }
    }

    private struct KeepOutItem: Identifiable {
        let choice: RadioController.KeepOut
        let label: String
        let sub: String
        var id: String { label }
    }

    @ViewBuilder
    private func keepOutButtons(menu: Bool) -> some View {
        let stationName = radio.currentStation?.name ?? "this station"
        let artist = (radio.track?.artist).flatMap { $0.isEmpty ? nil : $0 } ?? "this artist"
        let items = [
            KeepOutItem(choice: .skipOnce, label: "Skip this song", sub: "Just this once"),
            KeepOutItem(choice: .notOnStation, label: "Not on \(stationName)", sub: "This song stays off this station"),
            KeepOutItem(choice: .lessArtist, label: "Less \(artist) here", sub: "Plays them more rarely on this station"),
            KeepOutItem(choice: .neverArtist, label: "Never play \(artist)", sub: "Kept out of every station"),
        ]
        ForEach(items) { item in
            Button {
                skipMenuOpen = false
                Task { await radio.keepOut(item.choice) }
            } label: {
                if menu {
                    Text(item.label)
                } else {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(item.label).font(JukeFont.body(14, weight: .bold))
                        Text(item.sub).font(JukeFont.body(12)).foregroundStyle(theme.sub.color)
                    }
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .padding(.horizontal, 12)
                    .contentShape(Rectangle())
                }
            }
            .buttonStyle(.plain)
        }
    }

    private func saveMoment() async {
        if source == .radio {
            await radio.saveMoment()
            return
        }
        guard let track = model.detection.track else { return }
        var song = MemorySong(track: track)
        song.startSeconds = model.detection.estimatedPlaybackPosition().rounded(.down)
        var draft = MemoryDraft()
        draft.songs = [song]
        do {
            try await model.memories.save(draft)
            radio.notice = "Saved to Memories at \(RadioGesture.clock(song.startSeconds ?? 0))."
        } catch {
            radio.notice = (error as? LocalizedError)?.errorDescription ?? "Juke couldn’t save that moment."
        }
    }

    // MARK: Panels

    private var panelOverlay: some View {
        let open = panel != nil
        return ZStack(alignment: .topLeading) {
            theme.card.color
            switch panel {
            case .station?: StationSheet(close: { panel = nil })
            case .lyrics?: LyricsSheet(source: source, close: { panel = nil })
            case nil: EmptyView()
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .visualEffect { content, proxy in content.offset(y: open ? 0 : proxy.size.height) }
        .animation(reduceMotion ? nil : JukeMotion.easeOutSoft(0.52), value: open)
        .allowsHitTesting(open)
        .accessibilityHidden(!open)
    }
}
