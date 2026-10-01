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

    // MARK: Private state

    @ObservationIgnored private let backend: any RadioBackend
    @ObservationIgnored private let playback: any RadioPlaybackControlling
    @ObservationIgnored private let preferences: RadioPreferences
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
    @ObservationIgnored private var pollTask: Task<Void, Never>?
    @ObservationIgnored private var started = false

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

    /// Loads stations after sign-in and resumes radio when it was playing at quit.
    func start() async {
        guard !started else { return }
        started = true
        await loadStations()
        if let last = preferences.lastStationID, station(last) != nil { currentStationID = last }
        if currentStationID == nil { currentStationID = personalStation?.id }
        if hasTunedIn, preferences.wasPlaying { await resumeOnLaunch() }
    }

    /// Stops polling and forgets the session (sign-out). Preferences stay.
    func stop() {
        pollTask?.cancel()
        pollTask = nil
        started = false
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
        issue = nil
        notice = nil
        suggestion = nil
        summary = nil
        reactions = [:]
    }

    func loadStations() async {
        do {
            stations = try await backend.stations()
            stationsLoaded = true
            if issue == .signedOut { issue = nil }
        } catch is CancellationError {
        } catch {
            issue = RadioIssue.from(error, stationName: "Radio")
        }
    }

    private func resumeOnLaunch() async {
        // Never interrupt what is already playing: adopt it and keep the radio going after it.
        if let snapshot = try? await playback.state(), snapshot.isPlaying, let playing = snapshot.radioTrack {
            adopt(snapshot, track: playing)
            preferences.wasPlaying = true
            ensurePolling()
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
    func startNow(_ stationID: Radio.ID) async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        let name = station(stationID)?.name ?? "This station"
        do {
            let response = try await backend.playRadio(stationID: stationID, mode: .now, deviceID: deviceID, recentTrackIDs: recentTrackIDs)
            issue = nil
            notice = nil
            suggestion = nil
            currentStationID = stationID
            if pendingStationID == stationID { pendingStationID = nil }
            queuedTrack = nil
            queuedStationID = nil
            queueFailures = 0
            isPutAway = false
            isOnAir = true
            userPaused = false
            currentTrackSkipped = false
            expectedTrackID = response.track.spotifyId
            expectationDeadline = now().addingTimeInterval(Self.startGracePeriod)
            setTrack(response.track)
            remember(response.track.spotifyId)
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
        } catch is CancellationError {
        } catch {
            issue = RadioIssue.from(error, stationName: name)
        }
    }

    /// Handles a cross-section station request (Library "Start radio",
    /// New Station, "Start radio from this song").
    func handle(_ request: JukeCoordinator.StationRequest) async {
        if station(request.stationID) == nil { await loadStations() }
        guard let target = station(request.stationID) else { return }
        switch request.timing {
        case .afterCurrentSong where isOnAir && isPlaying:
            tune(to: target.id)
            notice = "\(target.name) starts when this song ends."
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

    func pause() async {
        guard isOnAir, isPlaying else { return }
        let position = position(at: now())
        do {
            try await playback.pause(deviceID: deviceID)
            userPaused = true
            setPosition(position, playing: false)
            preferences.wasPlaying = false
        } catch {
            issue = RadioIssue.from(error, stationName: currentStation?.name ?? "Radio")
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
        if isOnAir, isPlaying { await pause() }
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

    /// Tunes the dial: the station plays after the current song.
    func tune(to id: Radio.ID) {
        pendingStationID = id == currentStationID && (isOnAir || isPutAway) ? nil : id
        if !isOnAir, !isPutAway { currentStationID = id; pendingStationID = nil }
        suggestion = nil
        notice = nil
    }

    func tuneStep(_ direction: Int) -> FMDial.Mark? {
        let tuned = tunedStation?.frequency ?? FMDial.lowest
        guard let slot = FMDial.step(from: tuned, direction: direction, in: FMDial.slots(stations)) else { return nil }
        if case .station(let id) = slot.mark { tune(to: id) }
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

    func acceptSuggestion() {
        guard let offer = suggestion else { return }
        suggestion = nil
        pendingStationID = offer.stationId
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
    func moveStation(_ id: Radio.ID, to frequency: Double) async -> Double? {
        guard let station = station(id) else { return nil }
        let others = stations.filter { $0.id != id }.map(\.frequency)
        let proposal = FMDial.freeSlot(near: frequency, others: others)
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
        let snapshot: RadioPlaybackSnapshot?
        do {
            snapshot = try await playback.state()
        } catch is CancellationError {
            return
        } catch {
            issue = RadioIssue.from(error, stationName: currentStation?.name ?? "Radio")
            return
        }
        guard isOnAir else { return }
        guard let snapshot else {
            issue = .noActiveDevice
            if isPlaying { setPosition(position(at: now()), playing: false) }
            return
        }
        if issue == .noActiveDevice || issue == .spotifyFailed { issue = nil }
        deviceID = snapshot.deviceID ?? deviceID
        deviceName = snapshot.deviceName ?? deviceName
        let lastRemaining = duration - position(at: now())

        if let expected = expectedTrackID {
            if snapshot.trackID == expected {
                expectedTrackID = nil
            } else if now() < expectationDeadline {
                return
            } else {
                expectedTrackID = nil
            }
        }

        if let id = snapshot.trackID, id == track?.spotifyId {
            apply(snapshot)
        } else if let queued = queuedTrack, snapshot.trackID == queued.spotifyId {
            startQueued(queued, naturally: !currentTrackSkipped)
            apply(snapshot)
        } else {
            // Spotify moved on to something radio did not pick.
            goOffAir(notice: "Spotify is playing something else. Press play to bring the radio back.")
            return
        }

        if !snapshot.isPlaying, !userPaused, queuedTrack == nil,
           snapshot.progressMs == 0 || Double(snapshot.durationMs - snapshot.progressMs) / 1000 <= 2,
           lastRemaining <= Self.queueLeadTime + 5 {
            // The song ended with nothing queued: keep the music going.
            if let id = pendingStationID ?? currentStationID { await startNow(id) }
            return
        }
        await queueNextIfNeeded()
    }

    /// Queues the next pick when the current song has 20 s or less left.
    func queueNextIfNeeded() async {
        guard isOnAir, isPlaying, track != nil, queuedTrack == nil, !queueInFlight, queueFailures < 3 else { return }
        let remaining = duration - position(at: now())
        guard duration > 0, remaining <= Self.queueLeadTime else { return }
        guard let stationID = pendingStationID ?? currentStationID ?? personalStation?.id else { return }
        queueInFlight = true
        defer { queueInFlight = false }
        do {
            let response = try await backend.playRadio(stationID: stationID, mode: .queue, deviceID: deviceID, recentTrackIDs: recentTrackIDs)
            queuedTrack = response.track
            queuedStationID = stationID
            queueFailures = 0
            remember(response.track.spotifyId)
        } catch is CancellationError {
        } catch {
            queueFailures += 1
            issue = RadioIssue.from(error, stationName: station(stationID)?.name ?? "This station")
        }
    }

    private func startQueued(_ queued: Radio.Track, naturally: Bool) {
        if naturally, let previous = track {
            let previousStation = currentStationID
            Task { await self.post(.complete, track: previous, stationID: previousStation, positionMs: previous.durationMs) }
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
        remember(adopted.spotifyId)
        apply(snapshot)
    }

    private func goOffAir(notice message: String) {
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
            self?.pollTask = nil
        }
    }

    // MARK: Events

    private func post(_ event: Radio.Event, track: Radio.Track, stationID: Radio.ID?? = nil, positionMs: Int? = nil, artistID: String? = nil) async {
        var request = Radio.EventRequest(stationId: stationID ?? currentStationID, spotifyTrackId: track.spotifyId, event: event, positionMs: positionMs, source: "radio")
        if let artistID, !artistID.isEmpty { request.artistId = artistID }
        try? await backend.postEvent(request)
    }

    private func milliseconds(_ seconds: TimeInterval) -> Int { Int((max(0, seconds) * 1000).rounded()) }

    private func remember(_ trackID: String) {
        recentTrackIDs.removeAll { $0 == trackID }
        recentTrackIDs.append(trackID)
        if recentTrackIDs.count > 50 { recentTrackIDs.removeFirst(recentTrackIDs.count - 50) }
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
