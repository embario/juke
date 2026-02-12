import Foundation
import JukeCore

struct CatalogService {
    private let api: JukeAPIClient

    init(api: JukeAPIClient = .shared) {
        self.api = api
    }

    func searchTracks(query: String, token: String) async throws -> [CatalogTrack] {
        let queryItems = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "external", value: "true"),
        ]
        let response: CatalogSearchResponse = try await api.get("/api/v1/tracks/", token: token, queryItems: queryItems)
        return response.results
    }
}
