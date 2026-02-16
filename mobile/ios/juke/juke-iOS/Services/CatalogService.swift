import Foundation
import JukeKit

final class CatalogService {
    private let client: JukeAPIClient

    init(client: JukeAPIClient = .shared) {
        self.client = client
    }

    func fetchCatalog(token: String, query: String) async throws -> CatalogResults {
        async let artists: [Artist] = fetchCollection(resource: "artists", token: token, query: query)
        async let albums: [Album] = fetchCollection(resource: "albums", token: token, query: query)
        async let tracks: [Track] = fetchCollection(resource: "tracks", token: token, query: query)

        let results = try await (artists: artists, albums: albums, tracks: tracks)
        return CatalogResults(artists: results.artists, albums: results.albums, tracks: results.tracks)
    }

    private func fetchCollection<T: Decodable>(resource: String, token: String, query: String) async throws -> [T] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let queryItems: [URLQueryItem]? = trimmed.isEmpty ? nil : [
            URLQueryItem(name: "search", value: trimmed),
            URLQueryItem(name: "q", value: trimmed),
            URLQueryItem(name: "external", value: "true"),
        ]
        let response: JukePaginatedResponse<T> = try await client.send(
            "/api/v1/\(resource)/",
            token: token,
            queryItems: queryItems
        )
        return response.results
    }
}
