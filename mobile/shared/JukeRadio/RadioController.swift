import Foundation
import Observation

/// Drives Juke radio: stations, the tuned (pending) station, what Spotify is
/// playing, and the continuous-play loop.
///
/// Continuous play: while a radio song plays, about 20 s before it ends the
/// controller asks the server to queue the next pick
/// (`POST radio/play {mode: "queue"}`) from the pending station, or the
/// current one. When Spotify starts that queued song, the pending station
/// becomes current. Tuning only sets the pending station, so the music never
/// stops; the play cue ("switch now") uses `mode: "now"`.
///
/// Listening events: the server logs `play` itself for `mode: "now"`, so the
/// client posts `play` only when a queued song starts, `complete` when a
/// song ends naturally, and the explicit gestures (`skip`, `seek`, `save`,
/// `less`, `not_on_station`, `never_artist`).
@MainActor
@Observable
final class RadioController {
    /// Seconds before the end of a song when the next pick is queued.
    static let queueLeadTime: TimeInterval = 20
    /// A queued song that starts with this much (or less) of the previous
    /// one left counts as a natural finish (`complete`); earlier is a skip.
    static let naturalEndWindow: TimeInterval = 5
    /// How long a just-started song may take to show up in Spotify's state.
    static let startGracePeriod: TimeInterval = 8
    static let defaultStripEmoji = ["🔥", "🥹", "💃", "🌙", "☀️"]
    static let pickerEmoji = ["😌", "🔥", "🌙", "☀️", "💃", "🥹", "🧘", "🚗", "🌧️", "✨", "☕", "🤘",
                              "😭", "🥰", "😎", "🤯", "🫶", "🌊", "🍂", "❄️", "🌸", "🏃", "🛋️", "🎉"]

    // MARK: Stations

    private(set) var stations: [Radio.Station] = []
    private(set) var stationsLoaded = false
    private(set) var currentStationID: Radio.ID?
    /// The station tuned on the dial that takes over after the current song.
    private(set) var pendingStationID: Radio.ID?

    // MARK: Now playing

    private(set) var track: Radio.Track?
    private(set) var isPlaying = false
    /// Radio is in charge of playback (playing or paused by the listener).
    private(set) var isOnAir = false
    /// The record was slid back into its sleeve: paused, with a session summary.
    private(set) var isPutAway = false
    private(set) var queuedTrack: Radio.Track?
    private(set) var queuedStationID: Radio.ID?
    private(set) var deviceName: String?
    private(set) var isBusy = false
    private(set) var hasTunedIn: Bool

    // MARK: Feedback

    private(set) var issue: RadioIssue?
    /// Spotify is playing a podcast episode: radio stepped aside and offers to resume.
    private(set) var isPausedForEpisode = false
    /// The status line's message ("Noted. My Station will lean into 😌.").
    var notice: String?
    /// A better-matching station for the listener's reactions.
    private(set) var suggestion: Radio.StationSuggestion?
    private(set) var summary: Radio.SessionSummary?
    /// Reactions per Spotify track id.
    private(set) var reactions: [String: [String]] = [:]
    private(set) var customReactions: [String]

    /// Called whenever the playing song changes (artwork colour follows it).
    @ObservationIgnored var onTrackChange: (@MainActor (Radio.Track?) -> Void)?
    /// Every Spotify state radio reads. While radio is on air the app's
    /// recognition helper pauses its own Spotify polling and takes these instead.
    @ObservationIgnored var onSnapshot: (@MainActor (RadioPlaybackSnapshot) -> Void)?

    // MARK: Private state

    @ObservationIgnored private let backend: any RadioBackend
    @ObservationIgnored private let playback: any RadioPlaybackControlling
    @ObservationIgnored private var preferences: RadioPreferences
    @ObservationIgnored private let now: @MainActor () -> Date
    @ObservationIgnored private let saveMemory: @MainActor (MemoryDraft) async throws -> Void
    @ObservationIgnored private let autoPoll: Bool
    @ObservationIgnored private weak var coordinator: JukeCoordinator?

    private var anchorPosition: TimeInterval = 0
    private var anchorDate: Date
    @ObservationIgnored private var deviceID: String?
    @ObservationIgnored private var expectedTrackID: String?
    @ObservationIgnored private var expectationDeadline: Date = .distantPast
    @ObservationIgnored private var queueInFlight = false
    @ObservationIgnored private var queueFailures = 0
    @ObservationIgnored private var userPaused = false
    @ObservationIgnored private var currentTrackSkipped = false
    @ObservationIgnored private var recentTrackIDs: [String] = []
    /// Songs radio already played, oldest first, for Previous.
    @ObservationIgnored private(set) var playedHistory: [Radio.Track] = []
    @ObservationIgnored private var replayingPrevious = false
    @ObservationIgnored private var pollTask: Task<Void, Never>?
    @ObservationIgnored private var started = false
    /// Bumped on sign-out; responses from an older session are dropped.
    @ObservationIgnored private var generation = 0
    /// Every song radio picked this session, with the station it came from.
    @ObservationIgnored private var knownPicks: [String: (track: Radio.Track, stationID: Radio.ID?)] = [:]
    /// Queued picks Spotify will still play although radio moved on (its
    /// queue cannot be cleared); skipped when they start.
    @ObservationIgnored private var staleQueuedIDs: Set<String> = []
    /// Consecutive polls showing a song radio did not pick.
    @ObservationIgnored private var mismatchCount = 0
    /// Automatic restarts (song ended with nothing queued) back off after failures.
    @ObservationIgnored private var autoStartFailures = 0
    @ObservationIgnored private var nextAutoStart: Date = .distantPast
    /// The song ended with nothing queued; keep trying (with back-off) until a pick starts.
    @ObservationIgnored private var awaitingRestart = false
    /// The latest station asked for while a start was in flight.
    @ObservationIgnored private var deferredStart: Radio.ID?

    init(
        backend: any RadioBackend,
        playback: any RadioPlaybackControlling,
        preferences: RadioPreferences = RadioPreferences(),
        coordinator: JukeCoordinator? = nil,
        autoPoll: Bool = true,
        now: @escaping @MainActor () -> Date = { Date() },
        saveMemory: @escaping @MainActor (MemoryDraft) async throws -> Void = { _ in }
    ) {
        self.backend = backend
        self.playback = playback
        self.preferences = preferences
        self.coordinator = coordinator
        self.autoPoll = autoPoll
        self.now = now
        self.saveMemory = saveMemory
        anchorDate = now()
        hasTunedIn = preferences.hasTunedIn
        customReactions = preferences.customReactions
        observeStationRequests()
    }

    // MARK: Derived state

    func station(_ id: Radio.ID?) -> Radio.Station? {
        guard let id else { return nil }
        return stations.first { $0.id == id }
    }

    var personalStation: Radio.Station? { stations.first(where: \.isPersonal) ?? stations.first }
    var currentStation: Radio.Station? { station(currentStationID) ?? personalStation }
    var pendingStation: Radio.Station? { station(pendingStationID) }
    /// What the dial's needle points at.
    var tunedStation: Radio.Station? { pendingStation ?? currentStation }
    var duration: TimeInterval { track?.duration ?? 0 }

    func position(at date: Date) -> TimeInterval {
        let elapsed = isPlaying ? max(0, date.timeIntervalSince(anchorDate)) : 0
        let value = anchorPosition + elapsed
        return duration > 0 ? min(duration, value) : value
    }

    var currentReactions: [String] {
        guard let id = track?.spotifyId else { return [] }
        return reactions[id] ?? []
    }

    /// Chips for the reaction strip: the station's emoji feelings and a few
    /// defaults, the listener's own recent emoji, then whatever is selected.
    var stripReactions: [String] {
        let feelings = (currentStation?.feelings ?? []).filter(Self.isEmoji)
        let base = Self.unique(feelings + Self.defaultStripEmoji).prefix(5)
        let custom = customReactions.filter(Self.isEmoji).suffix(2)
        return Array(Self.unique(Array(base) + Array(custom) + currentReactions).prefix(9))
    }

    var pickerReactions: [String] {
        Array(Self.unique(Self.pickerEmoji + customReactions.filter(Self.isEmoji)).prefix(32))
    }

    // MARK: Lifecycle

    /// Loads stations after sign-in and resumes radio when it was playing at
    /// quit. Preferences are kept per account.
    func start(accountID: String? = nil) async {
        guard !started else { return }
        started = true
        if let accountID {
            preferences = preferences.scoped(to: accountID)
            hasTunedIn = preferences.hasTunedIn
            customReactions = preferences.customReactions
        }
        let session = generation
        await loadStations()
        guard session == generation else { return }
        if let last = preferences.lastStationID, station(last) != nil { currentStationID = last }
        if currentStationID == nil { currentStationID = personalStation?.id }
        if hasTunedIn, preferences.wasPlaying { await resumeOnLaunch() }
    }

    /// Stops polling and forgets the session (sign-out). Preferences stay.
    func stop() {
        pollTask?.cancel()
        pollTask = nil
        started = false
        generation += 1
        deviceID = nil
        deviceName = nil
        recentTrackIDs = []
        playedHistory = []
        knownPicks = [:]
        staleQueuedIDs = []
        expectedTrackID = nil
        expectationDeadline = .distantPast
        queueInFlight = false
        queueFailures = 0
        userPaused = false
        currentTrackSkipped = false
        mismatchCount = 0
        autoStartFailures = 0
        nextAutoStart = .distantPast
        awaitingRestart = false
        deferredStart = nil
        isBusy = false
        hasTunedIn = false
        customReactions = []
        preferences = preferences.scoped(to: nil)
        stations = []
        stationsLoaded = false
        currentStationID = nil
        pendingStationID = nil
        setTrack(nil)
        queuedTrack = nil
        queuedStationID = nil
        isPlaying = false
        isOnAir = false
        isPutAway = false
        isPausedForEpisode = false
        issue = nil
        notice = nil
        suggestion = nil
        summary = nil
        reactions = [:]
    }

    func loadStations() async {
        let session = generation
        do {
            let loaded = try await backend.stations()
            guard session == generation else { return }
            stations = loaded
            stationsLoaded = true
            if issue == .signedOut { issue = nil }
        } catch is CancellationError {
        } catch {
            guard session == generation else { return }
            issue = RadioIssue.from(error, stationName: "Radio")
        }
    }

    private func resumeOnLaunch() async {
        // Never interrupt what is already playing. A radio song still playing
        // is adopted and the radio carries on after it; anything else (another
        // playlist, a podcast) is left alone.
        let session = generation
        let snapshot = try? await playback.state()
        guard session == generation else { return }
        if let snapshot, snapshot.isPlaying {
            if snapshot.isEpisode {
                notice = Self.episodeNotice
                isPausedForEpisode = true
                preferences.wasPlaying = false
            } else if let playing = snapshot.radioTrack, preferences.recentRadioTrackIDs.contains(playing.spotifyId) {
                adopt(snapshot, track: playing)
                preferences.wasPlaying = true
                ensurePolling()
            } else {
                notice = "Spotify is playing something else. Press play to bring the radio back."
                preferences.wasPlaying = false
            }
            return
        }
        if let id = currentStationID ?? personalStation?.id { await startNow(id) }
    }

    // MARK: Turning radio on

    /// First run: start My Station.
    func tuneIn() async {
        if !stationsLoaded { await loadStations() }
        guard let id = personalStation?.id else { return }
        await startNow(id)
    }

    /// Plays the next pick from `stationID` immediately (`mode: "now"`).
    @discardableResult
    func startNow(_ stationID: Radio.ID) async -> Bool {
        guard !isBusy else {
            // Keep the latest request and run it when the current one finishes.
            deferredStart = stationID
            return false
        }
        isBusy = true
        let session = generation
        let started = await performStart(stationID, session: session)
        if session == generation { isBusy = false }
        if session == generation, let next = deferredStart {
            deferredStart = nil
            if next != currentStationID || !started { return await startNow(next) }
        }
        return started
    }

    private func performStart(_ stationID: Radio.ID, session: Int) async -> Bool {
        let name = station(stationID)?.name ?? "This station"
        do {
            let response = try await backend.playRadio(stationID: stationID, mode: .now, deviceID: deviceID, recentTrackIDs: recentTrackIDs)
            guard session == generation else { return false }
            // Spotify keeps an already-queued pick and plays it after this
            // song; skip it when it starts.
            if let stale = queuedTrack { staleQueuedIDs.insert(stale.spotifyId) }
            issue = nil
            notice = nil
            isPausedForEpisode = false
            suggestion = nil
            currentStationID = stationID
            if pendingStationID == stationID { pendingStationID = nil }
            queuedTrack = nil
            queuedStationID = nil
            queueFailures = 0
            autoStartFailures = 0
            nextAutoStart = .distantPast
            awaitingRestart = false
            mismatchCount = 0
            isPutAway = false
            isOnAir = true
            userPaused = false
            currentTrackSkipped = false
            expectedTrackID = response.track.spotifyId
            expectationDeadline = now().addingTimeInterval(Self.startGracePeriod)
            setTrack(response.track)
            remember(response.track, station: stationID)
            if let snapshot = RadioPlaybackSnapshot(json: response.state), snapshot.trackID == response.track.spotifyId {
                apply(snapshot)
            } else {
                setPosition(0, playing: true)
            }
            hasTunedIn = true
            preferences.hasTunedIn = true
            preferences.wasPlaying = true
            preferences.lastStationID = stationID
            ensurePolling()
            return true
        } catch is CancellationError {
            return false
        } catch {
            guard session == generation else { return false }
            issue = RadioIssue.from(error, stationName: name)
            return false
        }
    }

    /// Handles a cross-section station request (Library "Start radio",
    /// New Station, "Start radio from this song").
    func handle(_ request: JukeCoordinator.StationRequest) async {
        if station(request.stationID) == nil { await loadStations() }
        guard let target = station(request.stationID) else { return }
        switch request.timing {
        case .afterCurrentSong where isOnAir && isPlaying:
            await tune(to: target.id)
            if target.id != currentStationID { notice = "\(target.name) starts when this song ends." }
        default:
            await startNow(target.id)
        }
    }

    private func observeStationRequests() {
        guard let coordinator else { return }
        withObservationTracking {
            _ = coordinator.stationRequest
        } onChange: { [weak self] in
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.observeStationRequests()
                await self.consumeStationRequest()
            }
        }
    }

    func consumeStationRequest() async {
        guard let request = coordinator?.stationRequest else { return }
        coordinator?.stationRequest = nil
        await handle(request)
    }

    // MARK: Transport

    func togglePlayPause() async {
        if isPutAway { await comeBack(); return }
        if !isOnAir {
            if let id = pendingStationID ?? currentStation?.id { await startNow(id) }
            return
        }
        if isPlaying { await pause() } else { await resume() }
    }

    @discardableResult
    func pause() async -> Bool {
        guard isOnAir, isPlaying else { return true }
        let position = position(at: now())
        do {
            try await playback.pause(deviceID: deviceID)
            userPaused = true
            setPosition(position, playing: false)
            preferences.wasPlaying = false
            return true
        } catch {
            issue = RadioIssue.from(error, stationName: currentStation?.name ?? "Radio")
            return false
        }
    }

    func resume() async {
        guard isOnAir, !isPlaying else { return }
        let position = position(at: now())
        do {
            try await playback.resume(deviceID: deviceID)
            userPaused = false
            issue = nil
            setPosition(position, playing: true)
            preferences.wasPlaying = true
            ensurePolling()
        } catch {
            issue = RadioIssue.from(error, stationName: currentStation?.name ?? "Radio")
        }
    }

    /// Skips the song: plays the queued pick if there is one, otherwise a new
    /// pick from the tuned station.
    func skip() async {
        guard let playing = track, isOnAir else {
            if let id = pendingStationID ?? currentStation?.id { await startNow(id) }
            return
        }
        await post(.skip, track: playing, positionMs: milliseconds(position(at: now())))
        await advance()
    }

    /// Replays the song that played before this one on the station. With no
    /// earlier song it restarts the current one.
    func previous() async {
        guard isOnAir, track != nil else { return }
        guard let prior = playedHistory.last else { await seek(to: 0); return }
        do {
            try await playback.play(trackID: prior.spotifyId, deviceID: deviceID)
        } catch {
            issue = RadioIssue.from(error, stationName: currentStation?.name ?? "Radio")
            return
        }
        playedHistory.removeLast()
        replayingPrevious = true
        currentTrackSkipped = true
        expectedTrackID = prior.spotifyId
        expectationDeadline = now().addingTimeInterval(Self.startGracePeriod)
        issue = nil
        userPaused = false
        setTrack(prior)
        replayingPrevious = false
        setPosition(0, playing: true)
    }

    /// Moves on to the next song without logging a skip (the keep-out menu
    /// logs its own event).
    private func advance() async {
        currentTrackSkipped = true
        if let queued = queuedTrack {
            do {
                try await playback.next(deviceID: deviceID)
                startQueued(queued, naturally: false)
                expectedTrackID = queued.spotifyId
                expectationDeadline = now().addingTimeInterval(Self.startGracePeriod)
                return
            } catch {
                // Fall through to a fresh pick.
            }
        }
        if let id = pendingStationID ?? currentStationID ?? personalStation?.id { await startNow(id) }
    }

    func seek(to target: TimeInterval) async {
        guard let playing = track, isOnAir else { return }
        let clamped = max(0, duration > 0 ? min(duration - 0.5, target) : target)
        do {
            try await playback.seek(to: clamped, deviceID: deviceID)
            setPosition(clamped, playing: isPlaying)
            await post(.seek, track: playing, positionMs: milliseconds(clamped))
        } catch {
            issue = RadioIssue.from(error, stationName: currentStation?.name ?? "Radio")
        }
    }

    /// A spin of the record by `degrees` (see `VinylSeek`).
    func spin(degrees: Double) async {
        switch VinylSeek.outcome(position: position(at: now()), duration: duration, degrees: degrees) {
        case .seek(let target): await seek(to: target)
        case .advance: await skip()
        }
    }

    // MARK: Put away

    func putAway() async {
        // If Spotify would not pause, the record stays out and the error shows.
        guard await pause() else { return }
        isPutAway = true
        isOnAir = false
        notice = nil
        suggestion = nil
        preferences.wasPlaying = false
        summary = try? await backend.sessionSummary()
    }

    /// "Play again" / "Play <pending>" / sliding the record back out.
    func comeBack() async {
        guard isPutAway else { return }
        if let pending = pendingStationID {
            await startNow(pending)
            return
        }
        isPutAway = false
        isOnAir = track != nil
        if isOnAir {
            await resume()
            if !isPlaying, let id = currentStationID { await startNow(id) }
        } else if let id = currentStationID ?? personalStation?.id {
            await startNow(id)
        }
    }

    func saveSessionAsMemory() async {
        let summary: Radio.SessionSummary
        if let loaded = self.summary { summary = loaded } else {
            guard let loaded = try? await backend.sessionSummary() else {
                notice = "Juke couldn’t gather today’s listening. Try again in a moment."
                return
            }
            summary = loaded
            self.summary = loaded
        }
        guard !summary.tracks.isEmpty else {
            notice = "Nothing played this session yet."
            return
        }
        var draft = MemoryDraft()
        draft.occurredAt = summary.startedAt ?? now()
        let stationName = currentStation?.name ?? "the radio"
        draft.text = "\(summary.songCount) \(summary.songCount == 1 ? "song" : "songs") on \(stationName)."
        draft.songs = summary.tracks.prefix(12).map(Self.memorySong)
        draft.tags = MemoryDraft.normalizedTags(summary.reactions)
        do {
            try await saveMemory(draft)
            notice = "Saved today’s listening as a memory."
        } catch {
            notice = (error as? LocalizedError)?.errorDescription ?? "Juke couldn’t save that memory."
        }
    }

    /// The bookmark button: saves this moment to Memories.
    func saveMoment() async {
        guard let playing = track else { return }
        let at = position(at: now())
        await post(.save, track: playing, positionMs: milliseconds(at))
        var song = Self.memorySong(playing)
        song.startSeconds = at.rounded(.down)
        var draft = MemoryDraft()
        draft.songs = [song]
        draft.tags = MemoryDraft.normalizedTags(currentReactions)
        do {
            try await saveMemory(draft)
            let feel = currentReactions.prefix(3).joined(separator: " ")
            notice = "Saved to Memories at \(RadioGesture.clock(at))" + (feel.isEmpty ? "." : " with \(feel).")
            suggestion = nil
        } catch {
            notice = (error as? LocalizedError)?.errorDescription ?? "Juke couldn’t save that moment."
        }
    }

    // MARK: Tuning

    /// Tunes the dial: the station plays after the current song. If a pick
    /// from another station is already queued, a pick from the tuned station
    /// is queued too and the stale one is skipped when it starts, so the
    /// change still lands after this song.
    func tune(to id: Radio.ID) async {
        pendingStationID = id == currentStationID && (isOnAir || isPutAway) ? nil : id
        if !isOnAir, !isPutAway { currentStationID = id; pendingStationID = nil }
        suggestion = nil
        notice = nil
        let target = pendingStationID ?? currentStationID
        if isOnAir, let queued = queuedTrack, queuedStationID != target {
            staleQueuedIDs.insert(queued.spotifyId)
            queuedTrack = nil
            queuedStationID = nil
            queueFailures = 0
            await queueNextIfNeeded()
        }
    }

    func tuneStep(_ direction: Int) async -> FMDial.Mark? {
        let tuned = tunedStation?.frequency ?? FMDial.lowest
        guard let slot = FMDial.step(from: tuned, direction: direction, in: FMDial.slots(stations)) else { return nil }
        if case .station(let id) = slot.mark { await tune(to: id) }
        return slot.mark
    }

    /// The play cue next to the tuned station: switch now.
    func switchNow() async {
        guard let id = pendingStationID ?? currentStationID else { return }
        await startNow(id)
    }

    // MARK: Reactions

    func toggleReaction(_ reaction: String) async {
        var next = currentReactions
        if let index = next.firstIndex(of: reaction) { next.remove(at: index) } else { next.append(reaction) }
        await setReactions(next)
    }

    /// "In your words": saved exactly like an emoji.
    func addWords(_ text: String) async {
        let words = Self.normalizedWords(text)
        guard !words.isEmpty else { return }
        rememberCustom(words)
        guard !currentReactions.contains(words) else { return }
        await setReactions(currentReactions + [words])
    }

    func setReactions(_ next: [String]) async {
        guard let playing = track else { return }
        let station = currentStation
        reactions[playing.spotifyId] = next
        suggestion = nil
        notice = nil
        do {
            let response = try await backend.setReactions(spotifyTrackID: playing.spotifyId, stationID: station?.id, reactions: next)
            reactions[playing.spotifyId] = response.reactions
            if let offer = response.suggestion, offer.stationId != currentStationID, pendingStationID == nil, !next.isEmpty {
                suggestion = offer
            } else if !next.isEmpty, let station {
                notice = "Noted. \(station.name) will lean into \(next.suffix(3).joined(separator: " "))."
            }
        } catch {
            notice = "Juke couldn’t save that feeling. Try again in a moment."
        }
    }

    func acceptSuggestion() async {
        guard let offer = suggestion else { return }
        suggestion = nil
        await tune(to: offer.stationId)
    }

    func dismissSuggestion() {
        suggestion = nil
        if let station = currentStation {
            notice = "\(station.name) will lean into \(currentReactions.prefix(3).joined(separator: " "))."
        }
    }

    // MARK: Keep out (Skip's hold menu)

    enum KeepOut: CaseIterable, Sendable {
        case skipOnce, notOnStation, lessArtist, neverArtist
    }

    func keepOut(_ choice: KeepOut) async {
        guard let playing = track else { return }
        let station = currentStation
        let stationName = station?.name ?? "this station"
        let artist = playing.artist.isEmpty ? "this artist" : playing.artist
        switch choice {
        case .skipOnce:
            await skip()
            return
        case .notOnStation:
            await post(.notOnStation, track: playing)
            await advance()
            notice = "\(playing.title) is out of \(stationName)."
        case .lessArtist:
            await post(.less, track: playing)
            await advance()
            notice = "Less \(artist) on \(stationName)."
        case .neverArtist:
            await post(.neverArtist, track: playing, artistID: playing.artistId)
            await advance()
            notice = "\(artist) is kept out of all your stations."
        }
        await loadStations()
    }

    // MARK: Station sheet

    func removeSeed(_ seed: Radio.Seed, from stationID: Radio.ID) async {
        guard let station = station(stationID) else { return }
        await update(stationID, Radio.UpdateStationRequest(seeds: station.seeds.filter { $0 != seed }))
    }

    func removeFeeling(_ feeling: String, from stationID: Radio.ID) async {
        guard let station = station(stationID) else { return }
        await update(stationID, Radio.UpdateStationRequest(feelings: station.feelings.filter { $0 != feeling }))
    }

    func setLearning(_ learning: Bool, for stationID: Radio.ID) async {
        await update(stationID, Radio.UpdateStationRequest(learning: learning))
    }

    func addExclusion(_ text: String, to stationID: Radio.ID) async {
        let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return }
        do {
            _ = try await backend.addExclusion(stationID: stationID, Radio.CreateExclusionRequest(scope: .station, kind: .text, value: value, label: value))
            await loadStations()
        } catch {
            notice = "Juke couldn’t keep that out. Try again in a moment."
        }
    }

    func restoreExclusion(_ exclusion: Radio.Exclusion, on stationID: Radio.ID) async {
        do {
            try await backend.deleteExclusion(exclusion.id)
            await loadStations()
            if let station = station(stationID) { notice = "\(exclusion.label.isEmpty ? exclusion.value : exclusion.label) can play on \(station.name) again." }
        } catch {
            notice = "Juke couldn’t change that. Try again in a moment."
        }
    }

    /// Commits a station moved on the dial. The server snaps and spaces the
    /// frequency; the returned value wins.
    @discardableResult
    func moveStation(_ id: Radio.ID, to frequency: Double, preferring direction: Int = 0) async -> Double? {
        guard let station = station(id) else { return nil }
        let others = stations.filter { $0.id != id }.map(\.frequency)
        let proposal = FMDial.freeSlot(near: frequency, others: others, preferring: direction)
        guard abs(proposal - station.frequency) >= 0.05 else { return station.frequency }
        do {
            let updated = try await backend.updateStation(id, Radio.UpdateStationRequest(frequency: proposal))
            replace(updated)
            notice = "\(updated.name) now lives at \(updated.frequencyLabel) FM."
            return updated.frequency
        } catch {
            notice = "Juke couldn’t move \(station.name). Try again in a moment."
            return nil
        }
    }

    /// Sleeve: "Start radio from this song".
    func startRadioFromCurrentTrack() async {
        guard let playing = track else { return }
        let seed = Radio.Seed(kind: .track, spotifyId: playing.spotifyId, title: playing.title, subtitle: playing.artist, artworkUrl: playing.artworkUrl)
        do {
            let created = try await backend.createStation(name: nil, seeds: [seed], feelings: [])
            replace(created)
            if let coordinator { coordinator.requestStation(created.id, timing: .now) } else { await startNow(created.id) }
        } catch {
            notice = "Juke couldn’t start that station. Try again in a moment."
        }
    }

    private func update(_ id: Radio.ID, _ changes: Radio.UpdateStationRequest) async {
        do {
            replace(try await backend.updateStation(id, changes))
        } catch {
            notice = "Juke couldn’t change that. Try again in a moment."
        }
    }

    private func replace(_ station: Radio.Station) {
        if let index = stations.firstIndex(where: { $0.id == station.id }) { stations[index] = station } else { stations.append(station) }
        stations.sort { $0.frequency < $1.frequency }
    }

    // MARK: Polling and the continuous-play loop

    /// Reads Spotify's state once and runs the continuous-play loop.
    func refresh() async {
        guard isOnAir else { return }
        let session = generation
        let snapshot: RadioPlaybackSnapshot?
        do {
            snapshot = try await playback.state()
        } catch is CancellationError {
            return
        } catch {
            guard session == generation else { return }
            issue = RadioIssue.from(error, stationName: currentStation?.name ?? "Radio")
            return
        }
        guard session == generation, isOnAir else { return }
        guard let snapshot else {
            issue = .noActiveDevice
            if isPlaying { setPosition(position(at: now()), playing: false) }
            return
        }
        onSnapshot?(snapshot)
        if snapshot.isEpisode {
            // Never show an episode as a station song or queue songs behind it.
            if snapshot.isPlaying { yieldToEpisode() }
            return
        }
        if issue == .noActiveDevice || issue == .spotifyFailed { issue = nil }
        deviceID = snapshot.deviceID ?? deviceID
        deviceName = snapshot.deviceName ?? deviceName
        // A state without a song (between tracks, an ad) says nothing.
        guard let playingID = snapshot.trackID, !playingID.isEmpty else { return }
        let lastRemaining = duration - position(at: now())

        if staleQueuedIDs.contains(playingID), playingID != track?.spotifyId {
            // A pick queued before a station change (Spotify's queue cannot be
            // cleared): move past it to the tuned station's pick.
            mismatchCount = 0
            staleQueuedIDs.remove(playingID)
            try? await playback.next(deviceID: deviceID)
            if let queued = queuedTrack {
                expectedTrackID = queued.spotifyId
                expectationDeadline = now().addingTimeInterval(Self.startGracePeriod)
            }
            return
        }

        if let expected = expectedTrackID {
            if playingID == expected {
                expectedTrackID = nil
            } else if now() < expectationDeadline {
                return
            } else {
                expectedTrackID = nil
            }
        }

        if playingID == track?.spotifyId {
            mismatchCount = 0
            apply(snapshot)
        } else if let queued = queuedTrack, playingID == queued.spotifyId {
            mismatchCount = 0
            startQueued(queued, naturally: !currentTrackSkipped && lastRemaining <= Self.naturalEndWindow)
            apply(snapshot)
        } else if let known = knownPicks[playingID] {
            // A song radio picked earlier this session (for example a pick
            // queued before a station change): it is still the radio.
            mismatchCount = 0
            let picked = known.track
            let stationID = known.stationID ?? currentStationID
            if let stationID { currentStationID = stationID }
            if pendingStationID == currentStationID { pendingStationID = nil }
            setTrack(picked)
            currentTrackSkipped = false
            apply(snapshot)
            let postStation = currentStationID
            Task { await self.post(.play, track: picked, stationID: postStation, positionMs: 0) }
        } else {
            // Spotify moved on to something radio did not pick. One odd poll
            // is not enough to take the radio off the air.
            mismatchCount += 1
            if mismatchCount >= 2 {
                mismatchCount = 0
                goOffAir(notice: "Spotify is playing something else. Press play to bring the radio back.")
            }
            return
        }

        if snapshot.isPlaying { awaitingRestart = false }
        let atEnd = snapshot.progressMs == 0 || Double(snapshot.durationMs - snapshot.progressMs) / 1000 <= 2
        if !snapshot.isPlaying, !userPaused, queuedTrack == nil, atEnd,
           awaitingRestart || lastRemaining <= Self.queueLeadTime + 5 {
            awaitingRestart = true
            // The song ended with nothing queued: keep the music going, but
            // back off after failures instead of retrying every poll.
            guard now() >= nextAutoStart, let id = pendingStationID ?? currentStationID else { return }
            if isBusy {
                // This request is deferred behind a real start attempt; leave retry state alone.
                _ = await startNow(id)
            } else if await startNow(id) {
                autoStartFailures = 0
            } else if session == generation {
                autoStartFailures += 1
                nextAutoStart = now().addingTimeInterval(Self.retryDelay(afterFailures: autoStartFailures))
            }
            return
        }
        await queueNextIfNeeded()
    }

    /// 5 s, 10 s, 20 s … capped at 5 minutes.
    static func retryDelay(afterFailures failures: Int) -> TimeInterval {
        min(300, 5 * pow(2, Double(max(0, failures - 1))))
    }

    /// Queues the next pick when the current song has 20 s or less left.
    func queueNextIfNeeded() async {
        guard isOnAir, isPlaying, track != nil, queuedTrack == nil, !queueInFlight, queueFailures < 3 else { return }
        let remaining = duration - position(at: now())
        guard duration > 0, remaining <= Self.queueLeadTime else { return }
        guard let stationID = pendingStationID ?? currentStationID ?? personalStation?.id else { return }
        let session = generation
        queueInFlight = true
        defer { if session == generation { queueInFlight = false } }
        do {
            let response = try await backend.playRadio(stationID: stationID, mode: .queue, deviceID: deviceID, recentTrackIDs: recentTrackIDs)
            guard session == generation else { return }
            queuedTrack = response.track
            queuedStationID = stationID
            queueFailures = 0
            remember(response.track, station: stationID)
        } catch is CancellationError {
        } catch {
            guard session == generation else { return }
            queueFailures += 1
            issue = RadioIssue.from(error, stationName: station(stationID)?.name ?? "This station")
        }
    }

    private func startQueued(_ queued: Radio.Track, naturally: Bool) {
        if let previous = track {
            let previousStation = currentStationID
            // `complete` only for a natural finish; the skip paths post their own event.
            if naturally {
                Task { await self.post(.complete, track: previous, stationID: previousStation, positionMs: previous.durationMs) }
            } else if !currentTrackSkipped {
                let at = milliseconds(position(at: now()))
                Task { await self.post(.skip, track: previous, stationID: previousStation, positionMs: at) }
            }
        }
        if let stationID = queuedStationID {
            currentStationID = stationID
            if pendingStationID == stationID { pendingStationID = nil }
            preferences.lastStationID = stationID
        }
        queuedTrack = nil
        queuedStationID = nil
        currentTrackSkipped = false
        suggestion = nil
        setTrack(queued)
        setPosition(0, playing: true)
        let stationID = currentStationID
        Task { await self.post(.play, track: queued, stationID: stationID, positionMs: 0) }
    }

    private func adopt(_ snapshot: RadioPlaybackSnapshot, track adopted: Radio.Track) {
        isOnAir = true
        isPutAway = false
        userPaused = false
        setTrack(adopted)
        remember(adopted, station: currentStationID)
        apply(snapshot)
    }

    static let episodeNotice = "Spotify is playing something else. Radio is paused."

    private func yieldToEpisode() {
        goOffAir(notice: Self.episodeNotice)
        isPausedForEpisode = true
    }

    private func goOffAir(notice message: String) {
        isPausedForEpisode = false
        isOnAir = false
        isPlaying = false
        queuedTrack = nil
        queuedStationID = nil
        notice = message
        preferences.wasPlaying = false
    }

    private func apply(_ snapshot: RadioPlaybackSnapshot) {
        deviceID = snapshot.deviceID ?? deviceID
        deviceName = snapshot.deviceName ?? deviceName
        setPosition(TimeInterval(snapshot.progressMs) / 1000, playing: snapshot.isPlaying)
        if snapshot.isPlaying { userPaused = false }
    }

    private func setPosition(_ position: TimeInterval, playing: Bool) {
        anchorPosition = max(0, position)
        anchorDate = now()
        isPlaying = playing
    }

    private func setTrack(_ next: Radio.Track?) {
        guard next != track else { return }
        if !replayingPrevious, let old = track, next != nil, old.spotifyId != next?.spotifyId {
            playedHistory.append(old)
            if playedHistory.count > 20 { playedHistory.removeFirst(playedHistory.count - 20) }
        }
        track = next
        onTrackChange?(next)
    }

    private func ensurePolling() {
        guard autoPoll, pollTask == nil else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self, self.isOnAir else { break }
                await self.refresh()
                let remaining = self.duration - self.position(at: self.now())
                let untilQueue = remaining - Self.queueLeadTime
                var interval: TimeInterval = self.isPlaying ? 2 : 4
                if self.isPlaying, self.queuedTrack == nil, untilQueue > 0.2 { interval = min(interval, untilQueue) }
                try? await Task.sleep(for: .seconds(interval))
            }
            // A cancelled loop must not clear the handle of a newer one started after stop().
            if !Task.isCancelled { self?.pollTask = nil }
        }
    }

    // MARK: Events

    private func post(_ event: Radio.Event, track: Radio.Track, stationID: Radio.ID?? = nil, positionMs: Int? = nil, artistID: String? = nil) async {
        var request = Radio.EventRequest(stationId: stationID ?? currentStationID, spotifyTrackId: track.spotifyId, event: event, positionMs: positionMs, source: "radio")
        if let artistID, !artistID.isEmpty { request.artistId = artistID }
        try? await backend.postEvent(request)
    }

    private func milliseconds(_ seconds: TimeInterval) -> Int { Int((max(0, seconds) * 1000).rounded()) }

    private func remember(_ picked: Radio.Track, station stationID: Radio.ID?) {
        let trackID = picked.spotifyId
        recentTrackIDs.removeAll { $0 == trackID }
        recentTrackIDs.append(trackID)
        if recentTrackIDs.count > 50 { recentTrackIDs.removeFirst(recentTrackIDs.count - 50) }
        knownPicks[trackID] = (picked, stationID)
        preferences.recentRadioTrackIDs = Array(recentTrackIDs.suffix(10))
    }

    private func rememberCustom(_ reaction: String) {
        customReactions = Array(Self.unique(customReactions + [reaction]).suffix(24))
        preferences.customReactions = customReactions
    }

    // MARK: Helpers

    static func isEmoji(_ text: String) -> Bool {
        guard let first = text.unicodeScalars.first else { return false }
        return first.properties.isEmojiPresentation || (first.properties.isEmoji && text.unicodeScalars.count > 1)
    }

    /// Words as saved: trimmed, single spaces, at most 40 characters.
    static func normalizedWords(_ text: String) -> String {
        let collapsed = text.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        return String(collapsed.prefix(Radio.ReactionsRequest.maxPhraseLength))
    }

    static func unique(_ values: [String]) -> [String] {
        var seen = Set<String>()
        return values.filter { seen.insert($0).inserted }
    }

    static func memorySong(_ track: Radio.Track) -> MemorySong {
        var song = MemorySong(title: track.title, artist: track.artist, provider: "spotify", providerID: track.spotifyId,
                              playbackURL: URL(string: "spotify:track:\(track.spotifyId)"))
        song.artworkURL = track.artworkURL
        return song
    }
}
