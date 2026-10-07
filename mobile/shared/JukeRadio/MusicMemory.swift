import Foundation

struct MemorySong: Codable, Identifiable, Equatable, Sendable {
    var id: UUID = UUID()
    var title: String
    var artist: String
    var provider: String
    var providerID: String?
    var playbackURL: URL?
    var artworkURL: URL?
    var startSeconds: Double?
    var endSeconds: Double?

    enum CodingKeys: String, CodingKey {
        case id, title, artist, provider, artworkURL
        case providerID = "providerTrackID", playbackURL = "deepLink"
        case startSeconds = "segmentStartSeconds", endSeconds = "segmentEndSeconds"
    }

    init(track: RecognizedTrack) {
        title = track.title; artist = track.artist
        provider = track.providerNamespace == "spotify" ? "spotify" : "appleMusic"
        providerID = track.providerTrackID
        playbackURL = track.providerPlaybackURL ?? track.appleMusicURL
        artworkURL = track.artworkURL
    }

    init(title: String, artist: String, provider: String, providerID: String? = nil, playbackURL: URL? = nil) {
        self.title = title; self.artist = artist; self.provider = provider
        self.providerID = providerID; self.playbackURL = playbackURL
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decode(UUID.self, forKey: .id)
        title = try values.decode(String.self, forKey: .title)
        artist = try values.decode(String.self, forKey: .artist)
        provider = try values.decode(String.self, forKey: .provider)
        let rawID = try values.decodeIfPresent(String.self, forKey: .providerID)
        providerID = rawID?.isEmpty == false ? rawID : nil
        let link = try values.decodeIfPresent(String.self, forKey: .playbackURL)
        playbackURL = link?.isEmpty == false ? URL(string: link!) : nil
        let artwork = try values.decodeIfPresent(String.self, forKey: .artworkURL)
        artworkURL = artwork?.isEmpty == false ? URL(string: artwork!) : nil
        startSeconds = try values.decodeIfPresent(Double.self, forKey: .startSeconds)
        endSeconds = try values.decodeIfPresent(Double.self, forKey: .endSeconds)
    }

    var segmentDescription: String? {
        guard startSeconds != nil || endSeconds != nil else { return nil }
        let start = Self.timestamp(startSeconds ?? 0)
        return endSeconds.map { "\(start)–\(Self.timestamp($0))" } ?? "From \(start)"
    }

    static func timestamp(_ seconds: Double) -> String {
        let value = seconds.isFinite ? Int(min(604_800, max(0, seconds))) : 0
        return String(format: "%d:%02d", value / 60, value % 60)
    }
}

struct MemoryMedia: Codable, Identifiable, Equatable, Sendable {
    let id: UUID
    let kind: String
    let filename: String
    let contentType: String
    let url: String
}

struct MemoryClassification: Codable, Equatable, Sendable {
    var status: String
    var tags: [String] = []
    var model: String?
    var message: String?

    enum CodingKeys: String, CodingKey { case status, model, message }

    static let unavailable = Self(status: "unavailable", tags: [], model: nil, message: "Automatic tags aren’t connected yet. Your own tags are ready to use.")
}

struct MusicMemory: Codable, Identifiable, Equatable, Sendable {
    let id: UUID
    var title: String
    var text: String
    var occurredAt: Date
    var createdAt: Date
    var place: String
    var people: [String]
    var songs: [MemorySong]
    var media: [MemoryMedia]
    var tags: [String]
    var classification: MemoryClassification
    var generatedTags: [String] = []

    var displayTitle: String {
        if !title.isEmpty { return title }
        if let song = songs.first { return song.title }
        if !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return String(text.prefix(60)) }
        return "A little window back"
    }

    enum CodingKeys: String, CodingKey {
        case id, title, occurredAt, createdAt, place, people, songs, media, tags, classification, generatedTags
        case text = "body"
    }
}

struct MemoryDraft: Codable, Equatable, Sendable {
    var title = ""
    var text = ""
    var occurredAt = Date()
    var place = ""
    var people: [String] = []
    var songs: [MemorySong] = []
    var mediaIDs: [UUID] = []
    var tags: [String] = []
    var excludedTags: [String] = []

    enum CodingKeys: String, CodingKey {
        case title, occurredAt, place, people, songs, mediaIDs, tags, excludedTags
        case text = "body"
    }

    var canSave: Bool {
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !songs.isEmpty || !mediaIDs.isEmpty
    }

    var validationMessage: String? {
        if !canSave { return "Add a song, a photo or video, or a few words to save this moment." }
        for song in songs {
            if song.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return "Give each song a title." }
            if let start = song.startSeconds, !start.isFinite || start < 0 || start > 604_800 { return "A segment must start at zero seconds or later." }
            if let end = song.endSeconds, !end.isFinite || end <= (song.startSeconds ?? 0) || end > 604_800 { return "A segment must end after it starts." }
        }
        return nil
    }

    static func storyTags(_ text: String) -> [String] {
        guard let regex = try? NSRegularExpression(pattern: "(?<![\\p{L}\\p{N}_])#([\\p{L}\\p{N}_-]+)") else { return [] }
        let source = text as NSString
        return normalizedTags(regex.matches(in: text, range: NSRange(location: 0, length: source.length)).map { source.substring(with: $0.range(at: 1)) })
    }

    static func normalizedTags(_ values: [String]) -> [String] {
        var seen = Set<String>()
        return values.compactMap { value in
            let tag = String(value.trimmingCharacters(in: .whitespacesAndNewlines).prefix(60))
            guard !tag.isEmpty, seen.insert(tag.lowercased()).inserted else { return nil }
            return tag
        }
    }
}

struct MemoryInsights: Codable, Sendable {
    struct Connection: Codable, Identifiable, Sendable {
        var kind: String
        var label: String
        var count: Int
        var memoryIDs: [UUID]
        var id: String { "\(kind):\(label)" }
    }
    var question: String
    var connections: [Connection]
    enum CodingKeys: String, CodingKey { case question = "prompt", connections }
    static let empty = Self(question: "Which song takes you straight back to a person or a place?", connections: [])
}
