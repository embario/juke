import Foundation

struct CatalogService {
    private let api: APIClient

    init(api: APIClient = .shared) {
        self.api = api
    }

    func searchTracks(query: String, token: String) async throws -> [CatalogTrack] {
        let queryItems = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "external", value: "true"),
        ]
        let response: CatalogSearchResponse = try await api.get("/tracks/", token: token, queryItems: queryItems)
        return response.results
    }
}
