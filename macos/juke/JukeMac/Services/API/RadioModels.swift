import Foundation

/// Codable models for the Radio API contract
/// (`tasks/juke-app-implementation.md`, "Radio API contract").
///
/// Keys match the server's camelCase JSON exactly. String enums decode
/// unknown values to `.unknown` so a newer server never breaks an older app.
enum Radio {}

// MARK: - Shared helpers

/// A string enum that decodes values it does not know as `unknownCase`.
protocol UnknownCaseDecodable: RawRepresentable, Codable, Sendable where RawValue == String {
    static var unknownCase: Self { get }
}

extension UnknownCaseDecodable {
    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = Self(rawValue: raw) ?? Self.unknownCase
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }
}

extension Radio {
    /// Server identifiers may be integers or strings (UUIDs); both decode to
    /// this. It encodes back as a number when it is one.
    struct ID: Codable, Hashable, Sendable, CustomStringConvertible, ExpressibleByStringLiteral, ExpressibleByIntegerLiteral {
        let rawValue: String

        init(_ rawValue: String) { self.rawValue = rawValue }
        init(stringLiteral value: String) { rawValue = value }
        init(integerLiteral value: Int) { rawValue = String(value) }

        var description: String { rawValue }

        init(from decoder: Decoder) throws {
            let container = try decoder.singleValueContainer()
            if let number = try? container.decode(Int.self) {
                rawValue = String(number)
            } else {
                rawValue = try container.decode(String.self)
            }
        }

        func encode(to encoder: Encoder) throws {
            var container = encoder.singleValueContainer()
            if let number = Int(rawValue) { try container.encode(number) } else { try container.encode(rawValue) }
        }
    }

    /// Arbitrary JSON, for contract fields whose shape is owned by another
    /// service (for example the Spotify playback `state`).
    enum JSONValue: Codable, Hashable, Sendable {
        case null
        case bool(Bool)
        case number(Double)
        case string(String)
        case array([JSONValue])
        case object([String: JSONValue])

        init(from decoder: Decoder) throws {
            let container = try decoder.singleValueContainer()
            if container.decodeNil() { self = .null }
            else if let value = try? container.decode(Bool.self) { self = .bool(value) }
            else if let value = try? container.decode(Double.self) { self = .number(value) }
            else if let value = try? container.decode(String.self) { self = .string(value) }
            else if let value = try? container.decode([JSONValue].self) { self = .array(value) }
            else { self = .object(try container.decode([String: JSONValue].self)) }
        }

        func encode(to encoder: Encoder) throws {
            var container = encoder.singleValueContainer()
            switch self {
            case .null: try container.encodeNil()
            case .bool(let value): try container.encode(value)
            case .number(let value): try container.encode(value)
            case .string(let value): try container.encode(value)
            case .array(let value): try container.encode(value)
            case .object(let value): try container.encode(value)
            }
        }

        subscript(key: String) -> JSONValue? {
            if case .object(let object) = self { return object[key] }
            return nil
        }
    }
}

// MARK: - Contract types

extension Radio {
    /// `Track`: `{spotifyId, uri, title, artist, artistId, album, albumId, artworkUrl, durationMs}`
    struct Track: Codable, Hashable, Sendable, Identifiable {
        let spotifyId: String
        let uri: String
        let title: String
        let artist: String
        let artistId: String?
        let album: String?
        let albumId: String?
        let artworkUrl: String?
        let durationMs: Int

        var id: String { spotifyId }
        var artworkURL: URL? { artworkUrl.flatMap { URL(string: $0) } }
        var duration: TimeInterval { TimeInterval(durationMs) / 1_000 }
    }

    enum SeedKind: CaseIterable, UnknownCaseDecodable {
        typealias RawValue = String
        case track, artist, album, unknown
        static var unknownCase: SeedKind { .unknown }

        /// Accepts the plural spelling used by crate queries (`tracks`).
        init?(rawValue: String) {
            switch rawValue {
            case "track", "tracks": self = .track
            case "artist", "artists": self = .artist
            case "album", "albums": self = .album
            case "unknown": self = .unknown
            default: return nil
            }
        }

        var rawValue: String {
            switch self {
            case .track: "track"
            case .artist: "artist"
            case .album: "album"
            case .unknown: "unknown"
            }
        }

        /// The `kind` query value for `GET crate/`.
        var crateQueryValue: String { rawValue + "s" }
    }

    /// `Seed`: `{kind, spotifyId, title, subtitle, artworkUrl}`
    struct Seed: Codable, Hashable, Sendable, Identifiable {
        let kind: SeedKind
        let spotifyId: String
        let title: String
        let subtitle: String?
        let artworkUrl: String?

        var id: String { "\(kind.rawValue):\(spotifyId)" }
        var artworkURL: URL? { artworkUrl.flatMap { URL(string: $0) } }
    }

    enum ExclusionScope: String, CaseIterable, UnknownCaseDecodable {
        case station, everywhere, unknown
        static var unknownCase: ExclusionScope { .unknown }
    }

    enum ExclusionKind: String, CaseIterable, UnknownCaseDecodable {
        case track, artist, genre, text, unknown
        static var unknownCase: ExclusionKind { .unknown }
    }

    /// `Exclusion`: `{id, scope, kind, value, label}`
    struct Exclusion: Codable, Hashable, Sendable, Identifiable {
        let id: ID
        let scope: ExclusionScope
        let kind: ExclusionKind
        let value: String
        let label: String
    }

    enum StationKind: String, CaseIterable, UnknownCaseDecodable {
        case personal, custom, unknown
        static var unknownCase: StationKind { .unknown }
    }

    /// `Station`: `{id, name, kind, frequency, seeds, thumbnails, feelings, learning, exclusions, createdAt}`
    struct Station: Codable, Hashable, Sendable, Identifiable {
        let id: ID
        let name: String
        let kind: StationKind
        /// MHz, odd tenths between 88.1 and 107.9.
        let frequency: Double
        let seeds: [Seed]
        /// Up to three artwork URLs.
        let thumbnails: [String]
        let feelings: [String]
        let learning: Bool
        let exclusions: [Exclusion]
        let createdAt: Date

        var isPersonal: Bool { kind == .personal }
        var thumbnailURLs: [URL] { thumbnails.compactMap { URL(string: $0) } }
        /// "88.7"
        var frequencyLabel: String { String(format: "%.1f", frequency) }
    }

    static let frequencyRange: ClosedRange<Double> = 88.1...107.9

    /// Snaps to the nearest odd tenth in range, as the server does
    /// (ties go up: 88.2 becomes 88.3).
    static func snappedFrequency(_ value: Double) -> Double {
        let scaled = min(1079, max(881, value * 10))
        var tenths = Int(scaled.rounded())
        if tenths % 2 == 0 { tenths += scaled < Double(tenths) ? -1 : 1 }
        return Double(min(1079, max(881, tenths))) / 10
    }
}

// MARK: - Requests and responses

extension Radio {
    struct StationList: Codable, Hashable, Sendable {
        let stations: [Station]
    }

    /// `POST stations/`. Needs at least one seed or feeling.
    struct CreateStationRequest: Codable, Hashable, Sendable {
        var name: String?
        var seeds: [Seed]
        var feelings: [String]
    }

    /// `PATCH stations/<id>/`. Only non-nil fields are sent.
    struct UpdateStationRequest: Codable, Hashable, Sendable {
        var name: String?
        var frequency: Double?
        var seeds: [Seed]?
        var feelings: [String]?
        var learning: Bool?

        init(name: String? = nil, frequency: Double? = nil, seeds: [Seed]? = nil, feelings: [String]? = nil, learning: Bool? = nil) {
            self.name = name
            self.frequency = frequency
            self.seeds = seeds
            self.feelings = feelings
            self.learning = learning
        }
    }

    /// `POST stations/<id>/exclusions/`
    struct CreateExclusionRequest: Codable, Hashable, Sendable {
        var scope: ExclusionScope
        var kind: ExclusionKind
        var value: String
        var label: String
    }

    /// `PUT reactions/`. Reactions are emoji or short phrases (40 characters or fewer).
    struct ReactionsRequest: Codable, Hashable, Sendable {
        var spotifyTrackId: String
        var stationId: ID?
        var reactions: [String]

        static let maxPhraseLength = 40
    }

    struct StationSuggestion: Codable, Hashable, Sendable {
        let stationId: ID
        let name: String
        let matched: [String]
    }

    struct ReactionsResponse: Codable, Hashable, Sendable {
        let reactions: [String]
        let suggestion: StationSuggestion?
    }

    /// `POST stations/<id>/next`
    struct NextTracksRequest: Codable, Hashable, Sendable {
        /// 1-10, server default 3.
        var count: Int?
        var recentTrackIds: [String]?
    }

    enum PickSource: String, CaseIterable, UnknownCaseDecodable {
        case mlcore, metadata, artist, search, seed, unknown
        static var unknownCase: PickSource { .unknown }
    }

    struct NextTracksResponse: Codable, Hashable, Sendable {
        let tracks: [Track]
        let source: PickSource
    }

    enum PlayMode: String, Codable, CaseIterable, Sendable {
        /// Start the station's next track now.
        case now
        /// Add it to the Spotify queue (about 20 s before the current track ends).
        case queue
    }

    /// `POST play`
    struct PlayRequest: Codable, Hashable, Sendable {
        var stationId: ID
        var mode: PlayMode
        var deviceId: String?
    }

    struct PlayResponse: Codable, Hashable, Sendable {
        let track: Track
        let state: JSONValue?
    }

    enum Event: String, CaseIterable, UnknownCaseDecodable {
        case play, complete, skip, less, seek, save, recognized
        case notOnStation = "not_on_station"
        case neverArtist = "never_artist"
        case unknown
        static var unknownCase: Event { .unknown }
    }

    /// `POST events/` (204)
    struct EventRequest: Codable, Hashable, Sendable {
        var stationId: ID?
        var spotifyTrackId: String
        var event: Event
        var positionMs: Int?
        var source: String?
    }

    /// One record in the Library crate.
    struct CrateItem: Codable, Hashable, Sendable, Identifiable {
        let id: ID
        let kind: SeedKind
        let spotifyId: String
        let title: String
        let subtitle: String?
        let artworkUrl: String?
        let track: Track?

        var artworkURL: URL? { artworkUrl.flatMap { URL(string: $0) } }

        /// A seed for `POST stations/` ("Start radio").
        var seed: Seed { Seed(kind: kind, spotifyId: spotifyId, title: title, subtitle: subtitle, artworkUrl: artworkUrl) }
    }

    struct CrateResponse: Codable, Hashable, Sendable {
        let items: [CrateItem]
    }

    /// `GET session/summary`, for "Save as a memory" when radio is put away.
    struct SessionSummary: Codable, Hashable, Sendable {
        let startedAt: Date
        let songCount: Int
        let reactions: [String]
        let tracks: [Track]
    }
}
