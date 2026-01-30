//
//  MusicProfile.swift
//  juke-iOS
//
//  Created by Mario Barrenechea on 3/28/22.
//

import Foundation

struct MusicProfile: Identifiable, Codable {
    let id: Int
    let username: String
    let name: String?
    let displayName: String
    let tagline: String
    let bio: String
    let location: String
    let avatarURL: URL?
    let favoriteGenres: [String]
    let favoriteArtists: [String]
    let favoriteAlbums: [String]
    let favoriteTracks: [String]
    let onboardingCompletedAt: Date?
    let createdAt: Date?
    let modifiedAt: Date?
    let isOwner: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case username
        case name
        case displayName = "display_name"
        case tagline
        case bio
        case location
        case avatarURL = "avatar_url"
        case favoriteGenres = "favorite_genres"
        case favoriteArtists = "favorite_artists"
        case favoriteAlbums = "favorite_albums"
        case favoriteTracks = "favorite_tracks"
        case onboardingCompletedAt = "onboarding_completed_at"
        case createdAt = "created_at"
        case modifiedAt = "modified_at"
        case isOwner = "is_owner"
    }

    init(
        id: Int,
        username: String,
        name: String?,
        displayName: String,
        tagline: String,
        bio: String,
        location: String,
        avatarURL: URL?,
        favoriteGenres: [String],
        favoriteArtists: [String],
        favoriteAlbums: [String],
        favoriteTracks: [String],
        onboardingCompletedAt: Date?,
        createdAt: Date?,
        modifiedAt: Date?,
        isOwner: Bool
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

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)

        let avatarValue = try container.decodeIfPresent(String.self, forKey: .avatarURL)

        self.init(
            id: try container.decode(Int.self, forKey: .id),
            username: try container.decode(String.self, forKey: .username),
            name: try container.decodeIfPresent(String.self, forKey: .name),
            displayName: try container.decodeIfPresent(String.self, forKey: .displayName) ?? "",
            tagline: try container.decodeIfPresent(String.self, forKey: .tagline) ?? "",
            bio: try container.decodeIfPresent(String.self, forKey: .bio) ?? "",
            location: try container.decodeIfPresent(String.self, forKey: .location) ?? "",
            avatarURL: sanitizedURL(from: avatarValue),
            favoriteGenres: try container.decodeIfPresent([String].self, forKey: .favoriteGenres) ?? [],
            favoriteArtists: try container.decodeIfPresent([String].self, forKey: .favoriteArtists) ?? [],
            favoriteAlbums: try container.decodeIfPresent([String].self, forKey: .favoriteAlbums) ?? [],
            favoriteTracks: try container.decodeIfPresent([String].self, forKey: .favoriteTracks) ?? [],
            onboardingCompletedAt: try container.decodeIfPresent(Date.self, forKey: .onboardingCompletedAt),
            createdAt: try container.decodeIfPresent(Date.self, forKey: .createdAt),
            modifiedAt: try container.decodeIfPresent(Date.self, forKey: .modifiedAt),
            isOwner: try container.decode(Bool.self, forKey: .isOwner)
        )
    }

    var preferredName: String {
        if !displayName.isEmpty {
            return displayName
        }
        if let name, !name.isEmpty {
            return name
        }
        return username
    }
}

struct MusicProfileSummary: Identifiable, Codable {
    let username: String
    let displayName: String
    let tagline: String
    let avatarURL: URL?

    var id: String { username }

    enum CodingKeys: String, CodingKey {
        case username
        case displayName = "display_name"
        case tagline
        case avatarURL = "avatar_url"
    }

    init(
        username: String,
        displayName: String,
        tagline: String,
        avatarURL: URL?
    ) {
        self.username = username
        self.displayName = displayName
        self.tagline = tagline
        self.avatarURL = avatarURL
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let avatarValue = try container.decodeIfPresent(String.self, forKey: .avatarURL)
        self.init(
            username: try container.decode(String.self, forKey: .username),
            displayName: try container.decodeIfPresent(String.self, forKey: .displayName) ?? "",
            tagline: try container.decodeIfPresent(String.self, forKey: .tagline) ?? "",
            avatarURL: sanitizedURL(from: avatarValue)
        )
    }
}

private func sanitizedURL(from rawValue: String?) -> URL? {
    guard let rawValue else {
        return nil
    }
    let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else {
        return nil
    }
    return URL(string: trimmed)
}
