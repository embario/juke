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

/// Background recognition: while Settings > "Recognize music in the
/// background" is on and Juke radio is not playing, songs the user plays
/// elsewhere become `recognized` taste events (`POST radio/events/`).
///
/// It only listens to what `MusicDetectionController` already knows (player
/// metadata, Spotify playback state, and Shazam matches when the user picked
/// This Mac or Around Me). It never starts audio capture itself, so the
/// microphone and system-audio permission prompts stay exactly as they are.
/// It has no UI.
@MainActor
@Observable
final class BackgroundRecognizer {
    typealias Resolver = @MainActor (RecognizedTrack) async -> String?
    typealias Poster = @MainActor (Radio.EventRequest) async throws -> Void

    /// Whether background recognition may post right now (setting on, signed in).
    @ObservationIgnored var isEnabled: @MainActor () -> Bool
    /// Whether Juke radio is playing. Radio posts its own `play` events, so
    /// its songs are not recognized again. Radio sets this when it starts.
    @ObservationIgnored var isRadioPlaying: @MainActor () -> Bool = { false }

    private(set) var policy: RecognitionEventPolicy
    /// The last event that went out, for diagnostics and tests.
    private(set) var lastPosted: Radio.EventRequest?

    @ObservationIgnored private let resolveCatalog: Resolver
    @ObservationIgnored private let post: Poster
    @ObservationIgnored private let now: @MainActor () -> Date
    @ObservationIgnored private let sleep: @MainActor (TimeInterval) async throws -> Void
    @ObservationIgnored private var resolved: [String: String?] = [:]
    @ObservationIgnored private var candidateKey: String?
    @ObservationIgnored private(set) var pending: Task<Void, Never>?
    @ObservationIgnored private var observation: Task<Void, Never>?

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

    /// Follows the detection controller's current song for the app's lifetime.
    func follow(_ detection: MusicDetectionController) {
        observation?.cancel()
        observation = Task { [weak self, weak detection] in
            let changes = Observations { @MainActor [weak detection] in
                Snapshot(track: detection?.track, isAudible: (detection?.isPlaying ?? false) || (detection?.isAudioPresent ?? false))
            }
            for await snapshot in changes {
                guard let self, detection != nil else { return }
                self.observe(snapshot.track, isAudible: snapshot.isAudible)
            }
        }
    }

    private struct Snapshot: Sendable, Equatable {
        let track: RecognizedTrack?
        let isAudible: Bool
    }

    /// Call when the current song or its playing state changes. A song becomes
    /// a candidate when it starts playing and is posted once it has stayed
    /// on for the policy's dwell time.
    func observe(_ track: RecognizedTrack?, isAudible: Bool) {
        guard let track, isAudible, isEnabled(), !isRadioPlaying() else {
            cancelPending()
            return
        }
        let key = track.identityKey
        guard key != candidateKey else { return }
        cancelPending()
        candidateKey = key
        let dwell = policy.dwell
        pending = Task { [weak self] in
            do { try await self?.sleep(dwell) } catch { return }
            guard !Task.isCancelled else { return }
            await self?.commit(track, key: key)
        }
    }

    func cancelPending() {
        pending?.cancel()
        pending = nil
        candidateKey = nil
    }

    /// Resolves the song's Spotify ID and posts it when the rules allow.
    /// Returns whether an event went out.
    @discardableResult
    func commit(_ track: RecognizedTrack, key: String? = nil) async -> Bool {
        guard isEnabled(), !isRadioPlaying() else { return false }
        guard let spotifyID = await spotifyID(for: track), !Task.isCancelled else { return false }
        // Settings or radio may have changed while the catalog was searched.
        guard isEnabled(), !isRadioPlaying() else { return false }
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

    private func spotifyID(for track: RecognizedTrack) async -> String? {
        if let id = SpotifyTrackMatcher.spotifyID(for: track) { return id }
        let key = track.identityKey
        if let cached = resolved[key] { return cached }
        let id = await resolveCatalog(track)
        if resolved.count > 500 { resolved.removeAll() }
        resolved[key] = id
        return id
    }
}

extension BackgroundRecognizer {
    /// The app's recognizer: posts through `JukeAPI` and resolves Apple Music
    /// and Shazam songs through the existing catalog search.
    static func live(api: JukeAPI, settings: JukeSettings, token: @escaping @MainActor () -> String?, allowed: @escaping @MainActor () -> Bool) -> BackgroundRecognizer {
        let catalog = CatalogClient()
        return BackgroundRecognizer(
            isEnabled: { allowed() && settings.backgroundRecognitionEnabled && token() != nil },
            resolveCatalog: { track in
                guard let token = token() else { return nil }
                let results = try? await catalog.search(SpotifyTrackMatcher.searchQuery(for: track), kind: "tracks", token: token)
                return results.flatMap { SpotifyTrackMatcher.bestMatch(for: track, in: $0) }
            },
            post: { event in try await api.postEvent(event) }
        )
    }
}
