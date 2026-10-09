import Foundation

/// In-memory radio used by UI tests (`--uitesting`), so the Radio card can be
/// exercised without a server or Spotify. Never used in release builds' normal runs.
actor RadioFixtureBackend: RadioBackend {
    private var stationList: [Radio.Station]
    private var picks: [Radio.Track]
    private var pickIndex = 0
    private var exclusions: [Radio.Exclusion] = []
    private var playedTracks: [Radio.Track] = []
    private let playback: RadioFixturePlayback

    init(playback: RadioFixturePlayback) {
        self.playback = playback
        let created = Date(timeIntervalSince1970: 1_790_000_000)
        func seed(_ id: String, _ title: String, _ artist: String) -> Radio.Seed {
            Radio.Seed(kind: .track, spotifyId: id, title: title, subtitle: artist, artworkUrl: nil)
        }
        stationList = [
            Radio.Station(id: "00000000-0000-4000-8000-000000000001", name: "My Station", kind: .personal, frequency: 88.7,
                          seeds: [seed("fixture-blue", "Blue in Green", "Miles Davis")], thumbnails: [], feelings: ["😌", "☀️", "✨"],
                          learning: true, exclusions: [], createdAt: created),
            Radio.Station(id: "00000000-0000-4000-8000-000000000002", name: "Sunday Slow", kind: .custom, frequency: 92.3,
                          seeds: [seed("fixture-sunday", "Sunday Morning", "The Velvet Underground")], thumbnails: [], feelings: ["☕", "😌", "🌧️"],
                          learning: false, exclusions: [], createdAt: created),
            Radio.Station(id: "00000000-0000-4000-8000-000000000003", name: "Night Drive", kind: .custom, frequency: 97.1,
                          seeds: [seed("fixture-midnight", "Midnight City", "M83")], thumbnails: [], feelings: ["🌙", "🚗"],
                          learning: false, exclusions: [], createdAt: created),
        ]
        picks = [
            Radio.Track(spotifyId: "fixture-maria", uri: "spotify:track:fixture-maria", title: "Maria También", artist: "Khruangbin",
                        artistId: "fixture-khruangbin", album: "Con Todo El Mundo", albumId: "fixture-ctem", artworkUrl: nil, durationMs: 208_000),
            Radio.Track(spotifyId: "fixture-show", uri: "spotify:track:fixture-show", title: "Show Me How", artist: "Men I Trust",
                        artistId: "fixture-mit", album: "Oncle Jazz", albumId: "fixture-oj", artworkUrl: nil, durationMs: 215_000),
        ]
    }

    func stations() async throws -> [Radio.Station] { stationList }

    func createStation(name: String?, seeds: [Radio.Seed], feelings: [String]) async throws -> Radio.Station {
        let station = Radio.Station(id: Radio.ID(UUID().uuidString.lowercased()), name: name ?? "\(seeds.first?.title ?? "New") Radio",
                                    kind: .custom, frequency: 105.9, seeds: seeds, thumbnails: [], feelings: feelings,
                                    learning: true, exclusions: [], createdAt: .now)
        stationList.append(station)
        return station
    }

    func updateStation(_ id: Radio.ID, _ changes: Radio.UpdateStationRequest) async throws -> Radio.Station {
        guard let index = stationList.firstIndex(where: { $0.id == id }) else { throw JukeAPIError.notFound(code: nil, detail: nil) }
        let old = stationList[index]
        let updated = Radio.Station(id: old.id, name: changes.name ?? old.name, kind: old.kind,
                                    frequency: changes.frequency.map(FMDial.snap) ?? old.frequency, seeds: changes.seeds ?? old.seeds,
                                    thumbnails: old.thumbnails, feelings: changes.feelings ?? old.feelings, learning: changes.learning ?? old.learning,
                                    exclusions: old.exclusions, createdAt: old.createdAt)
        stationList[index] = updated
        return updated
    }

    func addExclusion(stationID: Radio.ID, _ exclusion: Radio.CreateExclusionRequest) async throws -> Radio.Exclusion {
        let created = Radio.Exclusion(id: Radio.ID(UUID().uuidString.lowercased()), scope: exclusion.scope, kind: exclusion.kind,
                                      value: exclusion.value, label: exclusion.label)
        if let index = stationList.firstIndex(where: { $0.id == stationID }) {
            let old = stationList[index]
            stationList[index] = Radio.Station(id: old.id, name: old.name, kind: old.kind, frequency: old.frequency, seeds: old.seeds,
                                               thumbnails: old.thumbnails, feelings: old.feelings, learning: old.learning,
                                               exclusions: old.exclusions + [created], createdAt: old.createdAt)
        }
        return created
    }

    func deleteExclusion(_ id: Radio.ID) async throws {
        stationList = stationList.map { old in
            Radio.Station(id: old.id, name: old.name, kind: old.kind, frequency: old.frequency, seeds: old.seeds, thumbnails: old.thumbnails,
                          feelings: old.feelings, learning: old.learning, exclusions: old.exclusions.filter { $0.id != id }, createdAt: old.createdAt)
        }
    }

    func setReactions(spotifyTrackID: String, stationID: Radio.ID?, reactions: [String]) async throws -> Radio.ReactionsResponse {
        let suggestion = reactions.contains("🌙") && stationID != stationList[2].id
            ? Radio.StationSuggestion(stationId: stationList[2].id, name: stationList[2].name, matched: ["🌙"]) : nil
        return Radio.ReactionsResponse(reactions: reactions, suggestion: suggestion)
    }

    func playRadio(stationID: Radio.ID, mode: Radio.PlayMode, deviceID: String?, recentTrackIDs: [String]) async throws -> Radio.PlayResponse {
        let track = picks[pickIndex % picks.count]
        pickIndex += 1
        playedTracks.append(track)
        if mode == .now { await playback.start(track) } else { await playback.enqueue(track) }
        return Radio.PlayResponse(track: track, state: nil, source: .seed)
    }

    func postEvent(_ event: Radio.EventRequest) async throws {}

    func sessionSummary() async throws -> Radio.SessionSummary {
        Radio.SessionSummary(startedAt: Date().addingTimeInterval(-1800), songCount: max(1, playedTracks.count), reactions: ["😌"], tracks: playedTracks)
    }
}

/// Simulated Spotify for UI tests: starts on "Blue in Green", follows play/pause/seek/next.
actor RadioFixturePlayback: RadioPlaybackControlling {
    static let initialTrackID = "0aWMVrwxPNYkKmFthzmpRi"
    private var current: Radio.Track? = Radio.Track(spotifyId: "0aWMVrwxPNYkKmFthzmpRi", uri: "spotify:track:0aWMVrwxPNYkKmFthzmpRi",
                                                    title: "Blue in Green", artist: "Miles Davis", artistId: "fixture-miles",
                                                    album: "Kind of Blue", albumId: "fixture-kob", artworkUrl: nil, durationMs: 327_000)
    private var queue: [Radio.Track] = []
    private var progress: TimeInterval = 96
    private var playing = true
    private var updatedAt = Date()
    /// `--uitesting-episode`: Spotify is playing a podcast until radio starts a station.
    private var episodePlaying = ProcessInfo.processInfo.arguments.contains("--uitesting-episode")

    private func settle() {
        if playing { progress += Date().timeIntervalSince(updatedAt) }
        updatedAt = Date()
        if let track = current, progress >= track.duration {
            if queue.isEmpty { progress = 0; playing = false } else { current = queue.removeFirst(); progress = 0 }
        }
    }

    private var known: [String: Radio.Track] = [:]

    func start(_ track: Radio.Track) { known[track.spotifyId] = track; episodePlaying = false; current = track; progress = 0; playing = true; updatedAt = Date() }
    func enqueue(_ track: Radio.Track) { known[track.spotifyId] = track; queue.append(track) }
    func play(trackID: String, deviceID: String?) async throws {
        guard let track = known[trackID] else { throw JukeAPIError.notFound(code: nil, detail: nil) }
        start(track)
    }

    func state() async throws -> RadioPlaybackSnapshot? {
        settle()
        if episodePlaying {
            var episode = RadioPlaybackSnapshot(trackID: nil, durationMs: 0, progressMs: 60_000, isPlaying: true, deviceID: "ui-test-device",
                                                deviceName: "Test Mac")
            episode.contentType = "episode"
            return episode
        }
        guard let current else { return nil }
        return RadioPlaybackSnapshot(trackID: current.spotifyId, title: current.title, artist: current.artist, artistID: current.artistId,
                                     album: current.album, albumID: current.albumId, durationMs: current.durationMs,
                                     progressMs: Int(progress * 1000), isPlaying: playing, deviceID: "ui-test-device", deviceName: "Test Mac")
    }

    func pause(deviceID: String?) async throws { settle(); playing = false }
    func resume(deviceID: String?) async throws { settle(); playing = true }
    func next(deviceID: String?) async throws {
        settle()
        if !queue.isEmpty { current = queue.removeFirst() }
        progress = 0
        playing = true
    }
    func seek(to position: TimeInterval, deviceID: String?) async throws { settle(); progress = position }
}
