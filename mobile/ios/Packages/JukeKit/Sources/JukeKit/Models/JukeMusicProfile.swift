import Foundation

/// A user's music profile containing their preferences and metadata.
public struct JukeMusicProfile: Codable, Identifiable, Sendable {
    public let id: Int
    public let username: String
    public let name: String?
    public let displayName: String?
    public let tagline: String?
    public let bio: String?
    public let location: String?
    public let avatarURL: URL?
    public let favoriteGenres: [String]
    public let favoriteArtists: [String]
    public let favoriteAlbums: [String]
    public let favoriteTracks: [String]
    public let onboardingCompletedAt: Date?
    public let createdAt: Date?
    public let modifiedAt: Date?
    public let isOwner: Bool

    /// The user's preferred display name.
    ///
    /// Returns `displayName` if set, otherwise `name`, otherwise `username`.
    public var preferredName: String {
        if let displayName, !displayName.isEmpty {
            return displayName
        }
        if let name, !name.isEmpty {
            return name
        }
        return username
    }

    enum CodingKeys: String, CodingKey {
        case id
        case username
        case name
        case displayName
        case tagline
        case bio
        case location
        // convertFromSnakeCase maps avatar_url -> avatarUrl (not avatarURL)
        case avatarURL = "avatarUrl"
        case favoriteGenres
        case favoriteArtists
        case favoriteAlbums
        case favoriteTracks
        case onboardingCompletedAt
        case createdAt
        case modifiedAt
        case isOwner
    }

    public init(
        id: Int,
        username: String,
        name: String? = nil,
        displayName: String? = nil,
        tagline: String? = nil,
        bio: String? = nil,
        location: String? = nil,
        avatarURL: URL? = nil,
        favoriteGenres: [String] = [],
        favoriteArtists: [String] = [],
        favoriteAlbums: [String] = [],
        favoriteTracks: [String] = [],
        onboardingCompletedAt: Date? = nil,
        createdAt: Date? = nil,
        modifiedAt: Date? = nil,
        isOwner: Bool = false
    ) {
        self.id = id
        self.username = username
        self.name = name
        self.displayName = displayName
        self.tagline = tagline
        self.bio = bio
        self.location = location
        self.avatarURL = avatarURL
        self.favoriteGenres = favoriteGenres
        self.favoriteArtists = favoriteArtists
        self.favoriteAlbums = favoriteAlbums
        self.favoriteTracks = favoriteTracks
        self.onboardingCompletedAt = onboardingCompletedAt
        self.createdAt = createdAt
        self.modifiedAt = modifiedAt
        self.isOwner = isOwner
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)

        id = try container.decode(Int.self, forKey: .id)
        username = try container.decode(String.self, forKey: .username)
        name = try container.decodeIfPresent(String.self, forKey: .name)
        displayName = try container.decodeIfPresent(String.self, forKey: .displayName)
        tagline = try container.decodeIfPresent(String.self, forKey: .tagline)
        bio = try container.decodeIfPresent(String.self, forKey: .bio)
        location = try container.decodeIfPresent(String.self, forKey: .location)

        // Handle avatar URL - may come as string that needs sanitization
        if let avatarValue = try container.decodeIfPresent(String.self, forKey: .avatarURL) {
            avatarURL = Self.sanitizedURL(from: avatarValue)
        } else {
            avatarURL = nil
        }

        favoriteGenres = try container.decodeIfPresent([String].self, forKey: .favoriteGenres) ?? []
        favoriteArtists = try container.decodeIfPresent([String].self, forKey: .favoriteArtists) ?? []
        favoriteAlbums = try container.decodeIfPresent([String].self, forKey: .favoriteAlbums) ?? []
        favoriteTracks = try container.decodeIfPresent([String].self, forKey: .favoriteTracks) ?? []
        onboardingCompletedAt = try container.decodeIfPresent(Date.self, forKey: .onboardingCompletedAt)
        createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt)
        modifiedAt = try container.decodeIfPresent(Date.self, forKey: .modifiedAt)
        isOwner = try container.decodeIfPresent(Bool.self, forKey: .isOwner) ?? false
    }

    private static func sanitizedURL(from rawValue: String?) -> URL? {
        guard let rawValue else { return nil }
        let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        return URL(string: trimmed)
    }
}

/// A summarized version of a music profile for lists and search results.
public struct JukeMusicProfileSummary: Codable, Identifiable, Sendable {
    public let username: String
    public let displayName: String?
    public let tagline: String?
    public let avatarURL: URL?

    public var id: String { username }

    /// The user's preferred display name.
    public var preferredName: String {
        if let displayName, !displayName.isEmpty {
            return displayName
        }
        return username
    }

    enum CodingKeys: String, CodingKey {
        case username
        case displayName
        case tagline
        // convertFromSnakeCase maps avatar_url -> avatarUrl (not avatarURL)
        case avatarURL = "avatarUrl"
    }

    public init(
        username: String,
        displayName: String? = nil,
        tagline: String? = nil,
        avatarURL: URL? = nil
    ) {
        self.username = username
        self.displayName = displayName
        self.tagline = tagline
        self.avatarURL = avatarURL
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        username = try container.decode(String.self, forKey: .username)
        displayName = try container.decodeIfPresent(String.self, forKey: .displayName)
        tagline = try container.decodeIfPresent(String.self, forKey: .tagline)

        if let avatarValue = try container.decodeIfPresent(String.self, forKey: .avatarURL) {
            let trimmed = avatarValue.trimmingCharacters(in: .whitespacesAndNewlines)
            avatarURL = trimmed.isEmpty ? nil : URL(string: trimmed)
        } else {
            avatarURL = nil
        }
    }
}
