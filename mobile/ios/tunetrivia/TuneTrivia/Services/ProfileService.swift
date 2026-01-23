//
//  ProfileService.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-22.
//

import Foundation

final class ProfileService {
    private let client: APIClient

    init(client: APIClient = .shared) {
        self.client = client
    }

    func fetchMyProfile(token: String) async throws -> MusicProfile {
        return try await client.send(
            "/api/v1/music-profiles/me/",
            method: .get,
            token: token
        )
    }

    func fetchProfile(username: String, token: String) async throws -> MusicProfile {
        return try await client.send(
            "/api/v1/music-profiles/\(username)/",
            method: .get,
            token: token
        )
    }
}
