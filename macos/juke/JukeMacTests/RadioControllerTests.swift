import XCTest
@testable import Juke

// MARK: - Fakes

private actor FakeBackend: RadioBackend {
    struct PlayCall: Equatable { let stationID: Radio.ID; let mode: Radio.PlayMode }

    var stationList: [Radio.Station]
    var plays: [PlayCall] = []
    var events: [Radio.EventRequest] = []
    var updates: [(Radio.ID, Radio.UpdateStationRequest)] = []
    var playError: Error?
    var nextTracks: [Radio.Track]
    var reactionSuggestion: Radio.StationSuggestion?
    var snappedFrequency: Double?
    var created: [Radio.Seed] = []

    init(stations: [Radio.Station], tracks: [Radio.Track]) {
        stationList = stations
        nextTracks = tracks
    }

    func setPlayError(_ error: Error?) { playError = error }
    func setSuggestion(_ suggestion: Radio.StationSuggestion?) { reactionSuggestion = suggestion }
    func setSnapped(_ value: Double?) { snappedFrequency = value }

    func stations() async throws -> [Radio.Station] { stationList }

    func createStation(name: String?, seeds: [Radio.Seed], feelings: [String]) async throws -> Radio.Station {
        created += seeds
        let station = makeStation("c", name: "\(seeds.first?.title ?? "") Radio", frequency: 105.9)
        stationList.append(station)
        return station
    }

    func updateStation(_ id: Radio.ID, _ changes: Radio.UpdateStationRequest) async throws -> Radio.Station {
        updates.append((id, changes))
        guard let old = stationList.first(where: { $0.id == id }) else { throw JukeAPIError.notFound(code: nil, detail: nil) }
        let updated = makeStation(old.id.rawValue, name: old.name, frequency: snappedFrequency ?? changes.frequency ?? old.frequency,
                                  kind: old.kind, learning: changes.learning ?? old.learning)
        stationList = stationList.map { $0.id == id ? updated : $0 }
        return updated
    }

    func addExclusion(stationID: Radio.ID, _ exclusion: Radio.CreateExclusionRequest) async throws -> Radio.Exclusion {
        Radio.Exclusion(id: "x1", scope: exclusion.scope, kind: exclusion.kind, value: exclusion.value, label: exclusion.label)
    }

    func deleteExclusion(_ id: Radio.ID) async throws {}

    func setReactions(spotifyTrackID: String, stationID: Radio.ID?, reactions: [String]) async throws -> Radio.ReactionsResponse {
        Radio.ReactionsResponse(reactions: reactions, suggestion: reactionSuggestion)
    }

    func playRadio(stationID: Radio.ID, mode: Radio.PlayMode, deviceID: String?, recentTrackIDs: [String]) async throws -> Radio.PlayResponse {
        if let playError { throw playError }
        plays.append(PlayCall(stationID: stationID, mode: mode))
        let track = nextTracks.isEmpty ? makeTrack("fallback") : nextTracks.removeFirst()
        return Radio.PlayResponse(track: track, state: nil, source: .seed)
    }

    func postEvent(_ event: Radio.EventRequest) async throws { events.append(event) }

    func sessionSummary() async throws -> Radio.SessionSummary {
        Radio.SessionSummary(startedAt: nil, songCount: 2, reactions: ["😌"], tracks: [makeTrack("a"), makeTrack("b")])
    }
}

private actor FakePlayback: RadioPlaybackControlling {
    var snapshot: RadioPlaybackSnapshot?
    var error: Error?
    var calls: [String] = []

    func set(_ snapshot: RadioPlaybackSnapshot?) { self.snapshot = snapshot }
    func setError(_ error: Error?) { self.error = error }

    func state() async throws -> RadioPlaybackSnapshot? {
        if let error { throw error }
        return snapshot
    }
    func pause(deviceID: String?) async throws { calls.append("pause") }
    func resume(deviceID: String?) async throws { calls.append("resume") }
    func next(deviceID: String?) async throws { calls.append("next") }
    func seek(to position: TimeInterval, deviceID: String?) async throws { calls.append("seek:\(Int(position))") }
}

@MainActor
private final class Clock {
    var now = Date(timeIntervalSince1970: 1_800_000_000)
    func advance(_ seconds: TimeInterval) { now = now.addingTimeInterval(seconds) }
}

private func makeTrack(_ id: String, duration: Int = 200_000, artistID: String? = "artist-\(UUID().uuidString.prefix(4))") -> Radio.Track {
    Radio.Track(spotifyId: id, uri: "spotify:track:\(id)", title: "Song \(id)", artist: "Artist \(id)", artistId: artistID,
                album: "Album", albumId: "album-\(id)", artworkUrl: nil, durationMs: duration)
}

private func makeStation(_ id: String, name: String, frequency: Double, kind: Radio.StationKind = .custom, learning: Bool = true) -> Radio.Station {
    Radio.Station(id: Radio.ID(id), name: name, kind: kind, frequency: frequency, seeds: [], thumbnails: [], feelings: ["😌"],
                  learning: learning, exclusions: [], createdAt: Date(timeIntervalSince1970: 0))
}

private func playing(_ track: Radio.Track, at seconds: TimeInterval, isPlaying: Bool = true) -> RadioPlaybackSnapshot {
    RadioPlaybackSnapshot(trackID: track.spotifyId, title: track.title, artist: track.artist, durationMs: track.durationMs,
                          progressMs: Int(seconds * 1000), isPlaying: isPlaying, deviceID: "device-1", deviceName: "Mac")
}

// MARK: - Tests

@MainActor
final class RadioControllerTests: XCTestCase {
    private var suiteName = ""
    private var defaults: UserDefaults!
    private var clock: Clock!
    private var backend: FakeBackend!
    private var playback: FakePlayback!
    private var savedMemories: [MemoryDraft] = []

    private let mine = makeStation("00000000-0000-4000-8000-000000000001", name: "My Station", frequency: 88.7, kind: .personal)
    private let night = makeStation("00000000-0000-4000-8000-000000000002", name: "Night Drive", frequency: 97.1)
    private let first = makeTrack("t1", artistID: "artist-1")
    private let second = makeTrack("t2")
    private let third = makeTrack("t3")

    override func setUp() {
        super.setUp()
        suiteName = "juke.radio.tests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
        clock = Clock()
        backend = FakeBackend(stations: [mine, night], tracks: [first, second, third])
        playback = FakePlayback()
        savedMemories = []
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        super.tearDown()
    }

    private func makeController(coordinator: JukeCoordinator? = nil) -> RadioController {
        let clock = clock!
        return RadioController(backend: backend, playback: playback, preferences: RadioPreferences(defaults: defaults),
                               coordinator: coordinator, autoPoll: false, now: { clock.now },
                               saveMemory: { [weak self] draft in self?.savedMemories.append(draft) })
    }

    private func onAir() async -> RadioController {
        let radio = makeController()
        await radio.start()
        await radio.tuneIn()
        await playback.set(playing(first, at: 0))
        return radio
    }

    func testFirstRunWaitsForTuneIn() async {
        let radio = makeController()
        await radio.start()
        XCTAssertFalse(radio.hasTunedIn)
        XCTAssertFalse(radio.isOnAir)
        let plays = await backend.plays
        XCTAssertTrue(plays.isEmpty)
        XCTAssertEqual(radio.currentStationID, mine.id)
    }

    func testTuneInStartsMyStationNowAndRemembersIt() async {
        let radio = makeController()
        await radio.start()
        await radio.tuneIn()
        let plays = await backend.plays
        XCTAssertEqual(plays, [.init(stationID: mine.id, mode: .now)])
        XCTAssertEqual(radio.track, first)
        XCTAssertTrue(radio.isOnAir)
        XCTAssertTrue(radio.isPlaying)
        let prefs = RadioPreferences(defaults: defaults)
        XCTAssertTrue(prefs.hasTunedIn)
        XCTAssertTrue(prefs.wasPlaying)
        XCTAssertEqual(prefs.lastStationID, mine.id)
        // The server logs `play` for mode "now" itself.
        let events = await backend.events
        XCTAssertTrue(events.isEmpty)
    }

    func testQueuesNextPickTwentySecondsBeforeTheEnd() async {
        let radio = await onAir()
        clock.advance(170)
        await playback.set(playing(first, at: 170))
        await radio.refresh()
        var plays = await backend.plays
        XCTAssertEqual(plays.count, 1, "30 s left: nothing queued yet")

        clock.advance(11)
        await playback.set(playing(first, at: 181))
        await radio.refresh()
        plays = await backend.plays
        XCTAssertEqual(plays.last, .init(stationID: mine.id, mode: .queue))
        XCTAssertEqual(radio.queuedTrack, second)

        // Only once.
        clock.advance(2)
        await playback.set(playing(first, at: 183))
        await radio.refresh()
        plays = await backend.plays
        XCTAssertEqual(plays.count, 2)
    }

    func testTuningNeverInterruptsAndThePendingStationTakesOverAfterTheSong() async {
        let radio = await onAir()
        radio.tune(to: night.id)
        XCTAssertEqual(radio.pendingStationID, night.id)
        XCTAssertEqual(radio.tunedStation?.id, night.id)
        var plays = await backend.plays
        XCTAssertEqual(plays.count, 1, "tuning only cues the station")

        clock.advance(185)
        await playback.set(playing(first, at: 185))
        await radio.refresh()
        plays = await backend.plays
        XCTAssertEqual(plays.last, .init(stationID: night.id, mode: .queue))

        clock.advance(16)
        await playback.set(playing(second, at: 1))
        await radio.refresh()
        XCTAssertEqual(radio.track, second)
        XCTAssertEqual(radio.currentStationID, night.id)
        XCTAssertNil(radio.pendingStationID)
        XCTAssertNil(radio.queuedTrack)
        try? await Task.sleep(for: .milliseconds(50))
        let events = await backend.events
        XCTAssertEqual(events.map(\.event), [.complete, .play])
        XCTAssertEqual(events.first?.spotifyTrackId, first.spotifyId)
        XCTAssertEqual(events.first?.stationId, mine.id)
        XCTAssertEqual(events.last?.spotifyTrackId, second.spotifyId)
        XCTAssertEqual(events.last?.stationId, night.id)
    }

    func testTuningBackToTheCurrentStationIsUndo() async {
        let radio = await onAir()
        radio.tune(to: night.id)
        radio.tune(to: mine.id)
        XCTAssertNil(radio.pendingStationID)
    }

    func testPlayCueSwitchesNow() async {
        let radio = await onAir()
        radio.tune(to: night.id)
        await radio.switchNow()
        let plays = await backend.plays
        XCTAssertEqual(plays.last, .init(stationID: night.id, mode: .now))
        XCTAssertEqual(radio.currentStationID, night.id)
        XCTAssertNil(radio.pendingStationID)
        XCTAssertEqual(radio.track, second)
    }

    func testSkipWithoutQueuePostsSkipAndPlaysANewPick() async {
        let radio = await onAir()
        clock.advance(30)
        await radio.skip()
        let events = await backend.events
        XCTAssertEqual(events.map(\.event), [.skip])
        XCTAssertEqual(events.first?.positionMs, 30_000)
        let plays = await backend.plays
        XCTAssertEqual(plays.last, .init(stationID: mine.id, mode: .now))
        XCTAssertEqual(radio.track, second)
    }

    func testSkipWithAQueuedPickAdvancesSpotify() async {
        let radio = await onAir()
        clock.advance(185)
        await playback.set(playing(first, at: 185))
        await radio.refresh()
        await radio.skip()
        let calls = await playback.calls
        XCTAssertEqual(calls, ["next"])
        let plays = await backend.plays
        XCTAssertEqual(plays.count, 2, "no extra pick when one is queued")
        XCTAssertEqual(radio.track, second)
        try? await Task.sleep(for: .milliseconds(50))
        let events = await backend.events
        XCTAssertEqual(events.map(\.event), [.skip, .play], "a skipped song is not 'complete'")
    }

    func testKeepOutNeverPlayArtistSendsTheArtistID() async {
        let radio = await onAir()
        await radio.keepOut(.neverArtist)
        let events = await backend.events
        XCTAssertEqual(events.first?.event, .neverArtist)
        XCTAssertEqual(events.first?.artistId, "artist-1")
        XCTAssertEqual(radio.track, second)
        XCTAssertEqual(radio.notice, "Artist t1 is kept out of all your stations.")
    }

    func testNotOnStationAndLessPostTheirEvents() async {
        let radio = await onAir()
        await radio.keepOut(.notOnStation)
        await radio.keepOut(.lessArtist)
        let events = await backend.events
        XCTAssertEqual(events.map(\.event), [.notOnStation, .less])
        XCTAssertEqual(events.first?.stationId, mine.id)
    }

    func testSeekPostsSeekEvent() async {
        let radio = await onAir()
        await radio.spin(degrees: 360)
        let calls = await playback.calls
        XCTAssertEqual(calls, ["seek:14"])
        let events = await backend.events
        XCTAssertEqual(events.map(\.event), [.seek])
        XCTAssertEqual(events.first?.positionMs, 14_000)
    }

    func testSpinningPastTheEndSkips() async {
        let radio = await onAir()
        clock.advance(195)
        await radio.spin(degrees: 360)
        let plays = await backend.plays
        XCTAssertEqual(plays.count, 2)
        XCTAssertEqual(radio.track, second)
    }

    func testSpotifyNotLinkedShowsConnect() async {
        await backend.setPlayError(JukeAPIError.rejected(status: 400, code: "playback_provider_not_linked", detail: "Connect a streaming provider to control playback."))
        let radio = makeController()
        await radio.start()
        await radio.tuneIn()
        XCTAssertEqual(radio.issue, .spotifyNotLinked)
        XCTAssertFalse(radio.isOnAir)
        XCTAssertFalse(radio.hasTunedIn)
    }

    func testProviderFailureAndNoTracks() async {
        let radio = makeController()
        await radio.start()
        await backend.setPlayError(JukeAPIError.server(status: 502, code: "playback_provider_failure", detail: nil))
        await radio.tuneIn()
        XCTAssertEqual(radio.issue, .spotifyFailed)
        await backend.setPlayError(JukeAPIError.rejected(status: 409, code: "radio_no_tracks", detail: "nothing"))
        await radio.startNow(night.id)
        XCTAssertEqual(radio.issue, .noTracks(stationName: "Night Drive"))
    }

    func testNullStateMeansNoActiveDevice() async {
        let radio = await onAir()
        clock.advance(10)
        await playback.set(nil)
        await radio.refresh()
        XCTAssertEqual(radio.issue, .noActiveDevice)
        XCTAssertFalse(radio.isPlaying)
        await playback.set(playing(first, at: 10))
        await radio.refresh()
        XCTAssertNil(radio.issue)
        XCTAssertTrue(radio.isPlaying)
    }

    func testAnotherSongInSpotifyTakesRadioOffAir() async {
        let radio = await onAir()
        clock.advance(10)
        await playback.set(playing(makeTrack("elsewhere"), at: 3))
        await radio.refresh()
        XCTAssertFalse(radio.isOnAir)
        XCTAssertFalse(RadioPreferences(defaults: defaults).wasPlaying)
    }

    func testJustStartedSongIsGivenTimeToAppear() async {
        let radio = makeController()
        await radio.start()
        await radio.tuneIn()
        await playback.set(playing(makeTrack("previous"), at: 100))
        clock.advance(2)
        await radio.refresh()
        XCTAssertTrue(radio.isOnAir, "Spotify may still report the old song for a moment")
    }

    func testResumesOnLaunchByAdoptingWhatIsPlaying() async {
        let prefs = RadioPreferences(defaults: defaults)
        prefs.hasTunedIn = true
        prefs.wasPlaying = true
        await playback.set(playing(first, at: 42))
        let radio = makeController()
        await radio.start()
        XCTAssertTrue(radio.isOnAir)
        XCTAssertEqual(radio.track?.spotifyId, first.spotifyId)
        XCTAssertEqual(radio.position(at: clock.now), 42, accuracy: 0.01)
        let plays = await backend.plays
        XCTAssertTrue(plays.isEmpty, "never interrupts what is playing")
    }

    func testResumesOnLaunchByStartingTheLastStationWhenSilent() async {
        let prefs = RadioPreferences(defaults: defaults)
        prefs.hasTunedIn = true
        prefs.wasPlaying = true
        prefs.lastStationID = night.id
        let radio = makeController()
        await radio.start()
        let plays = await backend.plays
        XCTAssertEqual(plays, [.init(stationID: night.id, mode: .now)])
    }

    func testDoesNotResumeWhenRadioWasPaused() async {
        let radio = await onAir()
        await radio.pause()
        XCTAssertFalse(RadioPreferences(defaults: defaults).wasPlaying)
        let relaunched = makeController()
        await relaunched.start()
        XCTAssertFalse(relaunched.isOnAir)
    }

    func testPutAwayPausesLoadsSummaryAndComesBack() async {
        let radio = await onAir()
        await radio.putAway()
        XCTAssertTrue(radio.isPutAway)
        XCTAssertFalse(radio.isOnAir)
        XCTAssertEqual(radio.summary?.songCount, 2)
        var calls = await playback.calls
        XCTAssertEqual(calls, ["pause"])
        await radio.comeBack()
        calls = await playback.calls
        XCTAssertEqual(calls, ["pause", "resume"])
        XCTAssertTrue(radio.isOnAir)
        XCTAssertTrue(radio.isPlaying)
    }

    func testSaveSessionAsMemory() async {
        let radio = await onAir()
        await radio.putAway()
        await radio.saveSessionAsMemory()
        XCTAssertEqual(savedMemories.count, 1)
        XCTAssertEqual(savedMemories.first?.songs.map(\.providerID), ["a", "b"])
        XCTAssertEqual(savedMemories.first?.tags, ["😌"])
        XCTAssertEqual(radio.notice, "Saved today’s listening as a memory.")
    }

    func testSaveMomentPostsSaveAndCreatesAMemory() async {
        let radio = await onAir()
        clock.advance(62)
        await radio.saveMoment()
        let events = await backend.events
        XCTAssertEqual(events.map(\.event), [.save])
        XCTAssertEqual(savedMemories.first?.songs.first?.startSeconds, 62)
        XCTAssertEqual(radio.notice, "Saved to Memories at 1:02.")
    }

    func testReactionsSuggestABetterStation() async {
        let radio = await onAir()
        await backend.setSuggestion(Radio.StationSuggestion(stationId: night.id, name: "Night Drive", matched: ["🌙"]))
        await radio.toggleReaction("🌙")
        XCTAssertEqual(radio.currentReactions, ["🌙"])
        XCTAssertEqual(radio.suggestion?.stationId, night.id)
        radio.acceptSuggestion()
        XCTAssertEqual(radio.pendingStationID, night.id)
        XCTAssertNil(radio.suggestion)
    }

    func testReactionWithoutSuggestionLeansIn() async {
        let radio = await onAir()
        await radio.toggleReaction("😌")
        XCTAssertEqual(radio.notice, "Noted. My Station will lean into 😌.")
        await radio.toggleReaction("😌")
        XCTAssertEqual(radio.currentReactions, [])
    }

    func testWordsAreSavedLikeEmojiAndRemembered() async {
        let radio = await onAir()
        await radio.addWords("  first   cold morning of fall  ")
        XCTAssertEqual(radio.currentReactions, ["first cold morning of fall"])
        XCTAssertEqual(RadioPreferences(defaults: defaults).customReactions, ["first cold morning of fall"])
        XCTAssertEqual(RadioController.normalizedWords(String(repeating: "a", count: 60)).count, 40)
    }

    func testMoveStationUsesTheServerFrequency() async {
        let radio = await onAir()
        await backend.setSnapped(95.3)
        let result = await radio.moveStation(night.id, to: 95.08)
        XCTAssertEqual(result, 95.3)
        XCTAssertEqual(radio.station(night.id)?.frequency, 95.3)
        let updates = await backend.updates
        XCTAssertEqual(updates.first?.1.frequency, 95.1, "the client proposes a snapped, spaced slot")
        XCTAssertEqual(radio.notice, "Night Drive now lives at 95.3 FM.")
    }

    func testMoveStationNextToAnotherIsSpacedApart() async {
        let radio = await onAir()
        _ = await radio.moveStation(night.id, to: 89.1)
        let updates = await backend.updates
        XCTAssertEqual(updates.first?.1.frequency, 90.9)
    }

    func testStationRequestFromAnotherSectionIsConsumed() async {
        let coordinator = JukeCoordinator()
        let radio = makeController(coordinator: coordinator)
        await radio.start()
        coordinator.requestStation(night.id, timing: .now)
        await radio.consumeStationRequest()
        XCTAssertNil(coordinator.stationRequest)
        let plays = await backend.plays
        XCTAssertEqual(plays.last, .init(stationID: night.id, mode: .now))
    }

    func testStationRequestAfterTheSongCuesIt() async {
        let radio = await onAir()
        await radio.handle(.init(stationID: night.id, timing: .afterCurrentSong))
        XCTAssertEqual(radio.pendingStationID, night.id)
        let plays = await backend.plays
        XCTAssertEqual(plays.count, 1)
    }

    func testStartRadioFromSongCreatesAStationSeededWithIt() async {
        let radio = await onAir()
        await radio.startRadioFromCurrentTrack()
        let seeds = await backend.created
        XCTAssertEqual(seeds.map(\.spotifyId), [first.spotifyId])
        XCTAssertEqual(seeds.first?.kind, .track)
        let plays = await backend.plays
        XCTAssertEqual(plays.last?.mode, .now)
        XCTAssertEqual(radio.currentStation?.name, "Song t1 Radio")
    }

    func testTrackChangesNotifyArtwork() async {
        let radio = makeController()
        var seen: [String?] = []
        radio.onTrackChange = { seen.append($0?.spotifyId) }
        await radio.start()
        await radio.tuneIn()
        await radio.skip()
        XCTAssertEqual(seen, ["t1", "t2"])
    }
}
