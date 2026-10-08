import XCTest
@testable import Juke

// MARK: - Fakes

private actor FakeBackend: RadioBackend {
    struct PlayCall: Equatable { let stationID: Radio.ID; let mode: Radio.PlayMode }

    var stationList: [Radio.Station]
    var plays: [PlayCall] = []
    var playAttempts = 0
    var playDelay: Duration?
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
    func setPlayDelay(_ delay: Duration?) { playDelay = delay }
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
        playAttempts += 1
        if let playDelay { try? await Task.sleep(for: playDelay) }
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
    var pauseError: Error?
    var calls: [String] = []

    func set(_ snapshot: RadioPlaybackSnapshot?) { self.snapshot = snapshot }
    func setPauseError(_ error: Error?) { pauseError = error }
    func setError(_ error: Error?) { self.error = error }

    func state() async throws -> RadioPlaybackSnapshot? {
        if let error { throw error }
        return snapshot
    }
    func pause(deviceID: String?) async throws {
        if let pauseError { throw pauseError }
        calls.append("pause")
    }
    func resume(deviceID: String?) async throws { calls.append("resume") }
    func next(deviceID: String?) async throws { calls.append("next") }
    func seek(to position: TimeInterval, deviceID: String?) async throws { calls.append("seek:\(Int(position))") }
    func play(trackID: String, deviceID: String?) async throws { calls.append("play:\(trackID)") }
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
        await radio.tune(to: night.id)
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
        await radio.tune(to: night.id)
        await radio.tune(to: mine.id)
        XCTAssertNil(radio.pendingStationID)
    }

    func testPlayCueSwitchesNow() async {
        let radio = await onAir()
        await radio.tune(to: night.id)
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

    func testPreviousReplaysThePrecedingStationSong() async {
        let radio = await onAir()
        await radio.skip()
        XCTAssertEqual(radio.track, second)
        await radio.previous()
        let calls = await playback.calls
        XCTAssertEqual(calls.last, "play:\(first.spotifyId)")
        XCTAssertEqual(radio.track, first)
        XCTAssertTrue(radio.isPlaying)
        // Going back does not stack the song we left, so a second Previous has nothing earlier.
        XCTAssertTrue(radio.playedHistory.isEmpty)
        await radio.previous()
        let after = await playback.calls
        XCTAssertEqual(after.last, "seek:0", "with no earlier song Previous restarts this one")
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
        XCTAssertTrue(radio.isOnAir, "one odd poll is not enough")
        clock.advance(2)
        await radio.refresh()
        XCTAssertFalse(radio.isOnAir)
        XCTAssertFalse(RadioPreferences(defaults: defaults).wasPlaying)
    }

    func testPodcastEpisodeTakesRadioOffAirImmediatelyAndCanResume() async {
        let radio = await onAir()
        clock.advance(10)
        var episode = RadioPlaybackSnapshot(trackID: nil, durationMs: 0, progressMs: 5000, isPlaying: true, deviceID: "device-1", deviceName: "Mac")
        episode.contentType = "episode"
        await playback.set(episode)
        await radio.refresh()
        XCTAssertFalse(radio.isOnAir)
        XCTAssertTrue(radio.isPausedForEpisode)
        XCTAssertEqual(radio.notice, "Spotify is playing something else. Radio is paused.")
        XCTAssertFalse(RadioPreferences(defaults: defaults).wasPlaying)
        let before = await backend.plays.count
        await radio.togglePlayPause()
        XCTAssertTrue(radio.isOnAir)
        XCTAssertFalse(radio.isPausedForEpisode)
        let after = await backend.plays.count
        XCTAssertEqual(after, before + 1, "resume starts the station again")
    }

    func testEpisodeDetectedFromURIWithoutContentType() {
        let snapshot = RadioPlaybackSnapshot(trackID: "e1", durationMs: 1, progressMs: 0, isPlaying: true, uri: "spotify:episode:e1")
        XCTAssertTrue(snapshot.isEpisode)
        XCTAssertFalse(playing(first, at: 0).isEpisode)
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
        prefs.recentRadioTrackIDs = [first.spotifyId]
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
        await radio.acceptSuggestion()
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

    // MARK: Review fixes

    func testSwitchingNowWithAQueuedPickSkipsTheStalePickAndStaysOnAir() async {
        let radio = await onAir()
        clock.advance(185)
        await playback.set(playing(first, at: 185))
        await radio.refresh()
        XCTAssertEqual(radio.queuedTrack, second)
        await radio.startNow(night.id)
        XCTAssertEqual(radio.track, third)
        XCTAssertNil(radio.queuedTrack)

        // Near the end of the new song, the next pick is queued from Night Drive.
        clock.advance(185)
        await playback.set(playing(third, at: 185))
        await radio.refresh()
        XCTAssertEqual(radio.queuedTrack?.spotifyId, "fallback")

        // Spotify still plays the stale pick first: radio moves past it.
        clock.advance(16)
        await playback.set(playing(second, at: 0))
        await radio.refresh()
        XCTAssertTrue(radio.isOnAir)
        XCTAssertEqual(radio.track, third)
        var calls = await playback.calls
        XCTAssertEqual(calls, ["next"])

        await playback.set(playing(makeTrack("fallback"), at: 1))
        await radio.refresh()
        XCTAssertEqual(radio.track?.spotifyId, "fallback")
        XCTAssertEqual(radio.currentStationID, night.id)
        calls = await playback.calls
        XCTAssertEqual(calls, ["next"])
    }

    func testTuningAfterThePickIsQueuedRequeuesFromTheTunedStation() async {
        let radio = await onAir()
        clock.advance(185)
        await playback.set(playing(first, at: 185))
        await radio.refresh()
        await radio.tune(to: night.id)
        var plays = await backend.plays
        XCTAssertEqual(plays.last, .init(stationID: night.id, mode: .queue))
        XCTAssertEqual(radio.queuedTrack, third)

        clock.advance(16)
        await playback.set(playing(second, at: 0))
        await radio.refresh()
        let calls = await playback.calls
        XCTAssertEqual(calls, ["next"], "the stale pick from My Station is skipped")
        await playback.set(playing(third, at: 1))
        await radio.refresh()
        XCTAssertEqual(radio.track, third)
        XCTAssertEqual(radio.currentStationID, night.id)
        XCTAssertNil(radio.pendingStationID)
        plays = await backend.plays
        XCTAssertEqual(plays.count, 3)
    }

    func testAKnownRadioPickIsAdoptedInsteadOfGoingOffAir() async {
        let radio = await onAir()
        clock.advance(185)
        await playback.set(playing(first, at: 185))
        await radio.refresh()
        await radio.skip()
        // Spotify reports the earlier radio pick again (for example after a
        // manual "previous" in Spotify).
        clock.advance(10)
        await playback.set(playing(first, at: 3))
        await radio.refresh()
        await radio.refresh()
        XCTAssertTrue(radio.isOnAir)
        XCTAssertEqual(radio.track, first)
    }

    func testSnapshotsWithoutASongAreIgnored() async {
        let radio = await onAir()
        clock.advance(10)
        await playback.set(RadioPlaybackSnapshot(trackID: nil, durationMs: 0, progressMs: 0, isPlaying: true))
        await radio.refresh()
        await radio.refresh()
        await radio.refresh()
        XCTAssertTrue(radio.isOnAir)
    }

    func testAfterSongRequestForTheCurrentStationShowsNoNotice() async {
        let radio = await onAir()
        await radio.handle(.init(stationID: mine.id, timing: .afterCurrentSong))
        XCTAssertNil(radio.notice)
        XCTAssertNil(radio.pendingStationID)
    }

    func testSignOutResetsStateAndDropsLateResponses() async {
        let radio = makeController()
        await radio.start(accountID: "listener-a")
        await backend.setPlayDelay(.milliseconds(150))
        let inFlight = Task { await radio.startNow(night.id) }
        try? await Task.sleep(for: .milliseconds(20))
        radio.stop()
        _ = await inFlight.value
        XCTAssertFalse(radio.isOnAir)
        XCTAssertNil(radio.track)
        XCTAssertFalse(radio.isBusy)
        XCTAssertFalse(radio.hasTunedIn)
    }

    func testPreferencesArePerAccount() async {
        let a = makeController()
        await a.start(accountID: "listener-a")
        await a.tuneIn()
        XCTAssertTrue(a.hasTunedIn)
        a.stop()

        let b = makeController()
        await b.start(accountID: "listener-b")
        XCTAssertFalse(b.hasTunedIn, "another listener on this Mac starts fresh")
        let plays = await backend.plays
        XCTAssertEqual(plays.count, 1)

        let again = makeController()
        await again.start(accountID: "listener-a")
        XCTAssertTrue(again.hasTunedIn)
    }

    func testRestartAfterTheSongEndsBacksOff() async {
        let radio = await onAir()
        clock.advance(199)
        await backend.setPlayError(JukeAPIError.server(status: 502, code: "playback_provider_failure", detail: nil))
        await playback.set(playing(first, at: 0, isPlaying: false))
        await radio.refresh()
        var attempts = await backend.playAttempts
        XCTAssertEqual(attempts, 2, "tune in + one restart")
        XCTAssertEqual(radio.issue, .spotifyFailed)

        clock.advance(4)
        await radio.refresh()
        attempts = await backend.playAttempts
        XCTAssertEqual(attempts, 2, "waits 5 s before the next try")

        clock.advance(2)
        await radio.refresh()
        attempts = await backend.playAttempts
        XCTAssertEqual(attempts, 3)

        clock.advance(6)
        await radio.refresh()
        attempts = await backend.playAttempts
        XCTAssertEqual(attempts, 3, "then 10 s")

        await backend.setPlayError(nil)
        clock.advance(5)
        await radio.refresh()
        XCTAssertEqual(radio.track, second)
        XCTAssertNil(radio.issue)
        XCTAssertEqual(RadioController.retryDelay(afterFailures: 1), 5)
        XCTAssertEqual(RadioController.retryDelay(afterFailures: 3), 20)
        XCTAssertEqual(RadioController.retryDelay(afterFailures: 20), 300)
    }

    func testDeferredAutoRestartDoesNotClearExistingBackoff() async {
        let radio = await onAir()
        await backend.setPlayError(JukeAPIError.server(status: 502, code: "playback_provider_failure", detail: nil))
        await playback.set(playing(first, at: 199, isPlaying: false))

        await radio.refresh()
        clock.advance(5)
        await radio.refresh()
        clock.advance(10)
        await radio.refresh()

        clock.advance(20)
        await backend.setPlayDelay(.milliseconds(150))
        let inFlightRestart = Task { await radio.refresh() }
        try? await Task.sleep(for: .milliseconds(20))
        await radio.refresh()
        await inFlightRestart.value

        let attemptsAfterFailedRestart = await backend.playAttempts
        clock.advance(6)
        await radio.refresh()
        var attemptsAfterDeferredRetry = await backend.playAttempts
        XCTAssertEqual(attemptsAfterDeferredRetry, attemptsAfterFailedRestart,
                       "a deferred restart must not reset the 40-second delay after four failures")

        clock.advance(34)
        await backend.setPlayDelay(nil)
        await radio.refresh()
        attemptsAfterDeferredRetry = await backend.playAttempts
        XCTAssertEqual(attemptsAfterDeferredRetry, attemptsAfterFailedRestart + 1,
                       "the next retry should run after 40 seconds, without counting the deferred request")
    }

    func testPutAwayStaysOutWhenSpotifyWillNotPause() async {
        let radio = await onAir()
        await playback.setPauseError(PlaybackClientError.unavailable(502))
        await radio.putAway()
        XCTAssertFalse(radio.isPutAway)
        XCTAssertTrue(radio.isOnAir)
        XCTAssertEqual(radio.issue, .spotifyFailed)
    }

    func testSnapshotsAreSharedWithTheRecognitionHelper() async {
        let radio = await onAir()
        var seen: [String?] = []
        radio.onSnapshot = { seen.append($0.trackID) }
        await radio.refresh()
        XCTAssertEqual(seen, [first.spotifyId])
    }

    func testAStartRequestedWhileBusyRunsAfterwards() async {
        let radio = makeController()
        await radio.start()
        await backend.setPlayDelay(.milliseconds(80))
        let firstStart = Task { await radio.startNow(mine.id) }
        try? await Task.sleep(for: .milliseconds(20))
        let deferred = await radio.startNow(night.id)
        XCTAssertFalse(deferred, "a queued request has not started yet")
        _ = await firstStart.value
        let plays = await backend.plays
        XCTAssertEqual(plays.map(\.stationID), [mine.id, night.id])
        XCTAssertEqual(radio.currentStationID, night.id)
    }

    func testAQueuedSongStartingEarlyIsASkipNotAComplete() async {
        let radio = await onAir()
        clock.advance(185)
        await playback.set(playing(first, at: 185))
        await radio.refresh()
        clock.advance(1)
        await playback.set(playing(second, at: 0))
        await radio.refresh()
        try? await Task.sleep(for: .milliseconds(50))
        let events = await backend.events
        XCTAssertEqual(events.map(\.event), [.skip, .play])
    }

    func testLaunchLeavesNonRadioPlaybackAlone() async {
        let prefs = RadioPreferences(defaults: defaults)
        prefs.hasTunedIn = true
        prefs.wasPlaying = true
        prefs.recentRadioTrackIDs = ["episode1"]
        await playback.set(RadioPlaybackSnapshot(trackID: "episode1", durationMs: 1_800_000, progressMs: 60_000, isPlaying: true,
                                                 uri: "spotify:episode:episode1"))
        let radio = makeController()
        await radio.start()
        XCTAssertFalse(radio.isOnAir, "a podcast is not a radio song")
        let plays = await backend.plays
        XCTAssertTrue(plays.isEmpty, "and is never interrupted")

        await playback.set(playing(makeTrack("someone-elses-playlist"), at: 30))
        let other = makeController()
        await other.start()
        XCTAssertFalse(other.isOnAir)
    }
}
