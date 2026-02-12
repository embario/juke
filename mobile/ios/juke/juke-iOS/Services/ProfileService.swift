import Foundation
import JukeCore

struct PaginatedResponse<T: Decodable>: Decodable {
    let results: [T]
}

final class ProfileService {
    private let client: JukeAPIClient

    init(client: JukeAPIClient = .shared) {
        self.client = client
    }

    func searchProfiles(token: String, query: String) async throws -> [MusicProfileSummary] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return [] }
        let queryItems = [URLQueryItem(name: "q", value: trimmed)]
        let response: PaginatedResponse<MusicProfileSummary> = try await client.send(
            "/api/v1/music-profiles/search/",
            token: token,
            queryItems: queryItems
        )
        return response.results
    }
}
