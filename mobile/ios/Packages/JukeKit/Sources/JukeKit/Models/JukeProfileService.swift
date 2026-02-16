import Foundation

/// Service for fetching user profiles.
public final class JukeProfileService: Sendable {
    private let client: JukeAPIClient

    /// Creates a profile service with the given API client.
    /// - Parameter client: The API client to use. Defaults to `.shared`.
    public init(client: JukeAPIClient = .shared) {
        self.client = client
    }

    /// Fetches the current user's music profile.
    /// - Parameter token: The authentication token.
    /// - Returns: The user's music profile.
    /// - Throws: `JukeAPIError` on failure.
    public func fetchMyProfile(token: String) async throws -> JukeMusicProfile {
        try await client.send(
            "/api/v1/music-profiles/me/",
            method: .get,
            token: token
        )
    }

    /// Fetches a user's music profile by username.
    /// - Parameters:
    ///   - username: The username to fetch.
    ///   - token: The authentication token.
    /// - Returns: The user's music profile.
    /// - Throws: `JukeAPIError` on failure.
    public func fetchProfile(username: String, token: String) async throws -> JukeMusicProfile {
        try await client.send(
            "/api/v1/music-profiles/\(username)/",
            method: .get,
            token: token
        )
    }

    /// Searches for user profiles matching a query.
    /// - Parameters:
    ///   - token: The authentication token.
    ///   - query: The search query.
    /// - Returns: Array of matching profile summaries.
    /// - Throws: `JukeAPIError` on failure.
    public func searchProfiles(token: String, query: String) async throws -> [JukeMusicProfileSummary] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return [] }

        let queryItems = [URLQueryItem(name: "q", value: trimmed)]
        let response: JukePaginatedResponse<JukeMusicProfileSummary> = try await client.send(
            "/api/v1/music-profiles/search/",
            method: .get,
            token: token,
            queryItems: queryItems
        )
        return response.results
    }
}
