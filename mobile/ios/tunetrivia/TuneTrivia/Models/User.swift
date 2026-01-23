//
//  User.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-22.
//

import Foundation

struct User: Codable, Identifiable {
    let id: Int
    let username: String
    let email: String
    let firstName: String
    let lastName: String

    enum CodingKeys: String, CodingKey {
        case id
        case username
        case email
        case firstName = "first_name"
        case lastName = "last_name"
    }

    var displayName: String {
        if !firstName.isEmpty || !lastName.isEmpty {
            return "\(firstName) \(lastName)".trimmingCharacters(in: .whitespaces)
        }
        return username
    }
}

struct MusicProfile: Codable, Identifiable {
    let id: Int
    let username: String
    let name: String?
    let displayName: String?
    let tagline: String?
    let bio: String?
    let location: String?
    let avatarUrl: String?
    let favoriteGenres: [String]?
    let favoriteArtists: [String]?
    let favoriteAlbums: [String]?
    let favoriteTracks: [String]?
    let createdAt: String?
    let modifiedAt: String?
    let isOwner: Bool?

    enum CodingKeys: String, CodingKey {
        case id
        case username
        case name
        case displayName = "display_name"
        case tagline
        case bio
        case location
        case avatarUrl = "avatar_url"
        case favoriteGenres = "favorite_genres"
        case favoriteArtists = "favorite_artists"
        case favoriteAlbums = "favorite_albums"
        case favoriteTracks = "favorite_tracks"
        case createdAt = "created_at"
        case modifiedAt = "modified_at"
        case isOwner = "is_owner"
    }
}
