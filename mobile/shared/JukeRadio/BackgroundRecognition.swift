import Foundation
import Observation

/// Decides when a recognized song becomes a taste signal: it must stay on
/// for a while (`dwell`), the same Spotify track is posted at most once per
/// `repeatWindow`, and no more than `maxPerHour` events go out in an hour.
/// Pure value type so the rules are unit-testable with explicit dates.
struct RecognitionEventPolicy: Sendable, Equatable {
    var dwell: TimeInterval = 30
    var repeatWindow: TimeInterval = 30 * 60
    var maxPerHour = 40

    private(set) var lastPosted: [String: Date] = [:]
    private(set) var postTimes: [Date] = []

    func shouldPost(spotifyID: String, at date: Date) -> Bool {
        if let last = lastPosted[spotifyID], date.timeIntervalSince(last) < repeatWindow { return false }
        return postTimes.filter { date.timeIntervalSince($0) < 3_600 }.count < maxPerHour
    }

    mutating func record(spotifyID: String, at date: Date) {
        lastPosted[spotifyID] = date
        postTimes.append(date)
        postTimes.removeAll { date.timeIntervalSince($0) >= 3_600 }
        lastPosted = lastPosted.filter { date.timeIntervalSince($0.value) < repeatWindow }
    }
}

/// Where a recognition came from, as the `source` of a `recognized` event.
enum RecognitionSource: String, Sendable {
    /// Spotify or Apple Music player metadata (or Spotify's playback state).
    case metadata
    /// A ShazamKit match on audio the user chose to share (This Mac or Around Me).
    case shazam

    init(track: RecognizedTrack) {
        self = track.shazamID?.isEmpty == false ? .shazam : .metadata
    }
}

/// Matches a recognized song against catalog search results to find its
/// Spotify track ID. Only a confident title + artist match counts; anything
/// else is skipped rather than guessed.
enum SpotifyTrackMatcher {
    static func spotifyID(for track: RecognizedTrack) -> String? {
        guard track.providerNamespace == "spotify", let id = track.providerTrackID, !id.isEmpty else { return nil }
        return id
    }

    static func searchQuery(for track: RecognizedTrack) -> String {
        "\(normalizedTitle(track.title)) \(track.artist)"
    }

    static func bestMatch(for track: RecognizedTrack, in results: [CatalogSearchResult]) -> String? {
        let title = normalizedTitle(track.title)
        let artists = artistNames(track.artist)
        guard !title.isEmpty else { return nil }
        return results.first { result in
            guard let id = result.spotifyID, !id.isEmpty, normalizedTitle(result.name) == title else { return false }
            let candidates = artistNames(result.artistNames ?? "")
            return !artists.isDisjoint(with: candidates)
        }?.spotifyID
    }

    /// Lowercased, without diacritics, bracketed qualifiers ("(Remastered 2009)")
    /// or dash suffixes ("- Live"), and with collapsed whitespace.
    static func normalizedTitle(_ value: String) -> String {
        var text = value.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
        text = text.replacingOccurrences(of: #"\s*[\(\[][^\)\]]*[\)\]]"#, with: "", options: .regularExpression)
        if let dash = text.range(of: " - ") { text = String(text[..<dash.lowerBound]) }
        return text.split(whereSeparator: \.isWhitespace).joined(separator: " ")
    }

    static func artistNames(_ value: String) -> Set<String> {
        let folded = value.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
        let parts = folded.replacingOccurrences(of: #"\s+(&|and|feat\.?|ft\.?|with|x)\s+"#, with: ",", options: .regularExpression)
            .split(separator: ",")
            .map { $0.split(whereSeparator: \.isWhitespace).joined(separator: " ") }
            .filter { !$0.isEmpty }
        return Set(parts)
    }
}

/// A song the user started from Memories ("Play the moment", the composer's
/// "Hear it"). Replaying your own memory is not listening elsewhere, so
/// background recognition ignores that song for a while.
struct MemoryPlaybackMark: Equatable, Sendable {
    static let window: TimeInterval = 15 * 60

    let providerID: String?
    let title: String
    let artist: String
    let startedAt: Date

    func matches(_ track: RecognizedTrack, at date: Date) -> Bool {
        guard date.timeIntervalSince(startedAt) < Self.window else { return false }
        if let providerID, !providerID.isEmpty, let other = track.providerTrackID,
           providerID.caseInsensitiveCompare(other) == .orderedSame { return true }
        return SpotifyTrackMatcher.normalizedTitle(title) == SpotifyTrackMatcher.normalizedTitle(track.title)
            && !SpotifyTrackMatcher.artistNames(artist).isDisjoint(with: SpotifyTrackMatcher.artistNames(track.artist))
    }
}

/// What background recognition listens to: the platform's detector of the song
/// playing elsewhere (`MusicDetectionController` on the Mac, the now-playing
/// observer on iOS). Properties must be observable so `follow` re-arms on change.
@MainActor
protocol RecognitionFeed: AnyObject {
    var track: RecognizedTrack? { get }
    var isPlaying: Bool { get }
    var isAudioPresent: Bool { get }
}

/// Background recognition: while Settings > "Recognize music in the
/// background" is on and Juke radio is not playing, songs the user plays
/// elsewhere become `recognized` taste events (`POST radio/events/`).
///
/// It only listens to what `MusicDetectionController` already knows (player
/// metadata, Spotify playback state, and Shazam matches when the user picked
/// This Mac or Around Me in Settings). It never starts audio capture or polls
/// Spotify itself, so the microphone and system-audio permission prompts stay
/// exactly as they are. It has no UI.
///
/// Rules: a song must stay on for `policy.dwell` (short silences of up to
/// `silenceGrace` don't reset it); a Shazam song must be matched at least
/// twice, the last time within `shazamFreshness`; songs Juke radio played or
/// queued and songs started from Memories are never posted.
@MainActor
@Observable
final class BackgroundRecognizer {
    /// Returns the Spotify ID, `nil` when the catalog has no confident match
    /// (cached), or throws when the search failed (not cached, retried later).
    typealias Resolver = @MainActor (RecognizedTrack) async throws -> String?
    typealias Poster = @MainActor (Radio.EventRequest) async throws -> Void

    /// Whether background recognition may post right now (setting on, signed in).
    @ObservationIgnored var isEnabled: @MainActor () -> Bool
    /// Whether Juke radio is on the air and playing. Radio posts its own
    /// `play` events, so nothing is recognized meanwhile.
    @ObservationIgnored var isRadioPlaying: @MainActor () -> Bool = { false }
    /// Whether radio has this Spotify track playing or queued right now.
    @ObservationIgnored var isRadioTrack: @MainActor (String) -> Bool = { _ in false }
    /// The song last started from Memories, if any.
    @ObservationIgnored var memoryPlayback: @MainActor () -> MemoryPlaybackMark? = { nil }
    @ObservationIgnored var silenceGrace: TimeInterval = 10
    @ObservationIgnored var shazamFreshness: TimeInterval = 60

    private(set) var policy: RecognitionEventPolicy
    /// The last event that went out, for diagnostics and tests.
    private(set) var lastPosted: Radio.EventRequest?

    private struct Candidate {
        let key: String
        var track: RecognizedTrack
        var sightings: Int
        var lastSeen: Date
    }

    @ObservationIgnored private let resolveCatalog: Resolver
    @ObservationIgnored private let post: Poster
    @ObservationIgnored private let now: @MainActor () -> Date
    @ObservationIgnored private let sleep: @MainActor (TimeInterval) async throws -> Void
    @ObservationIgnored private var resolved: [String: String?] = [:]
    @ObservationIgnored private var radioTrackIDs = Set<String>()
    @ObservationIgnored private var candidate: Candidate?
    @ObservationIgnored private var latest: (track: RecognizedTrack?, isAudible: Bool) = (nil, false)
    @ObservationIgnored private(set) var pending: Task<Void, Never>?
    @ObservationIgnored private var silence: Task<Void, Never>?

    init(
        policy: RecognitionEventPolicy = RecognitionEventPolicy(),
        isEnabled: @escaping @MainActor () -> Bool,
        resolveCatalog: @escaping Resolver,
        post: @escaping Poster,
        now: @escaping @MainActor () -> Date = { Date() },
        sleep: @escaping @MainActor (TimeInterval) async throws -> Void = { try await Task.sleep(for: .seconds($0)) }
    ) {
        self.policy = policy
        self.isEnabled = isEnabled
        self.resolveCatalog = resolveCatalog
        self.post = post
        self.now = now
        self.sleep = sleep
    }

    /// Follows the detection controller's current song (and the setting) for
    /// the app's lifetime: `withObservationTracking`, re-armed after each change.
    func follow(_ detection: any RecognitionFeed) {
        followed = detection
        track()
    }

    @ObservationIgnored private weak var followed: (any RecognitionFeed)?

    private func track() {
        guard let detection = followed else { return }
        let current = withObservationTracking {
            (detection.track, detection.isPlaying || detection.isAudioPresent, isEnabled())
        } onChange: { [weak self] in
            Task { @MainActor [weak self] in self?.track() }
        }
        observe(current.0, isAudible: current.1)
    }

    /// Call when the current song or its playing state changes.
    func observe(_ track: RecognizedTrack?, isAudible: Bool) {
        latest = (track, isAudible)
        guard let track, isEnabled(), !isRadioPlaying() else {
            cancelPending()
            return
        }
        let key = track.identityKey
        guard isAudible else {
            // A quiet passage or a short pause keeps the candidate for a moment.
            guard candidate != nil, silence == nil else { return }
            let grace = silenceGrace
            silence = Task { [weak self] in
                do { try await self?.sleep(grace) } catch { return }
                guard !Task.isCancelled else { return }
                self?.cancelPending()
            }
            return
        }
        silence?.cancel()
        silence = nil
        if var current = candidate, current.key == key {
            if current.track != track {
                // A new Shazam match (or fresher metadata) for the same song.
                current.track = track
                current.sightings += 1
                current.lastSeen = now()
                candidate = current
            }
            if pending != nil { return }
        } else {
            cancelPending()
            candidate = Candidate(key: key, track: track, sightings: 1, lastSeen: now())
        }
        let dwell = policy.dwell
        pending = Task { [weak self] in
            do { try await self?.sleep(dwell) } catch { return }
            guard !Task.isCancelled, let self, let latest = self.candidate, latest.key == key else { return }
            await self.commit(latest.track, key: key)
            if self.candidate?.key == key { self.pending = nil }
        }
    }

    /// Looks at the current song again, for example after sign-in or when
    /// the setting is turned on.
    func reevaluate() {
        observe(latest.track, isAudible: latest.isAudible)
    }

    func cancelPending() {
        pending?.cancel()
        pending = nil
        silence?.cancel()
        silence = nil
        candidate = nil
    }

    /// Forgets everything tied to an account or server (sign-out, server change).
    func reset() {
        cancelPending()
        resolved = [:]
        radioTrackIDs = []
        lastPosted = nil
        policy = RecognitionEventPolicy(dwell: policy.dwell, repeatWindow: policy.repeatWindow, maxPerHour: policy.maxPerHour)
    }

    /// Records a song Juke radio played or queued this session.
    func noteRadioTrack(_ spotifyID: String?) {
        guard let spotifyID, !spotifyID.isEmpty else { return }
        radioTrackIDs.insert(spotifyID)
    }

    /// Resolves the song's Spotify ID and posts it when the rules allow.
    /// `key` is set when the song came through `observe` (Shazam freshness
    /// applies). Returns whether an event went out.
    @discardableResult
    func commit(_ track: RecognizedTrack, key: String? = nil) async -> Bool {
        guard allowed(track) else { return false }
        if key != nil, RecognitionSource(track: track) == .shazam {
            guard let current = candidate, current.key == key, current.sightings >= 2,
                  now().timeIntervalSince(current.lastSeen) <= shazamFreshness else { return false }
        }
        guard let spotifyID = await spotifyID(for: track), !Task.isCancelled else { return false }
        // Settings, radio or memory playback may have changed while the catalog was searched.
        guard allowed(track), !radioTrackIDs.contains(spotifyID), !isRadioTrack(spotifyID) else { return false }
        let date = now()
        guard policy.shouldPost(spotifyID: spotifyID, at: date) else { return false }
        let event = Radio.EventRequest(
            stationId: nil,
            spotifyTrackId: spotifyID,
            event: .recognized,
            positionMs: nil,
            source: RecognitionSource(track: track).rawValue
        )
        // Record first so a slow request is never doubled by the next poll.
        policy.record(spotifyID: spotifyID, at: date)
        do {
            try await post(event)
            lastPosted = event
            return true
        } catch {
            // A taste signal is best effort; the song is not retried until the repeat window passes.
            return false
        }
    }

    private func allowed(_ track: RecognizedTrack) -> Bool {
        guard isEnabled(), !isRadioPlaying() else { return false }
        if let mark = memoryPlayback(), mark.matches(track, at: now()) { return false }
        return true
    }

    private func spotifyID(for track: RecognizedTrack) async -> String? {
        if let id = SpotifyTrackMatcher.spotifyID(for: track) { return id }
        let key = track.identityKey
        if let cached = resolved[key] { return cached }
        do {
            let id = try await resolveCatalog(track)
            if resolved.count > 500 { resolved.removeAll() }
            resolved[key] = id
            return id
        } catch {
            return nil
        }
    }
}

extension BackgroundRecognizer {
    /// The app's recognizer: posts through `JukeAPI` and resolves Apple Music
    /// and Shazam songs through the existing catalog search. `enabled` is the
    /// user's setting; the token and sign-in checks are added here.
    static func live(api: JukeAPI, enabled: @escaping @MainActor () -> Bool, token: @escaping @MainActor () -> String?, allowed: @escaping @MainActor () -> Bool) -> BackgroundRecognizer {
        let catalog = CatalogClient()
        return BackgroundRecognizer(
            isEnabled: { allowed() && enabled() && token() != nil },
            resolveCatalog: { track in
                guard let token = token() else { throw CancellationError() }
                let results = try await catalog.search(SpotifyTrackMatcher.searchQuery(for: track), kind: "tracks", token: token)
                return SpotifyTrackMatcher.bestMatch(for: track, in: results)
            },
            post: { event in try await api.postEvent(event) }
        )
    }
}
