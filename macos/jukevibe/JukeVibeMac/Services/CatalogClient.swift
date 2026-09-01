import Foundation

struct CatalogSearchResult: Decodable, Identifiable, Sendable {
    let pk: Int
    let name: String
    let spotifyID: String?
    let albumName: String?
    let artistNames: String?
    let spotifyData: SpotifyData?

    var id: Int { pk }
    struct SpotifyData: Decodable, Sendable { let images: [String]? }

    enum CodingKeys: String, CodingKey {
        case pk, name
        case spotifyID = "spotify_id"
        case albumName = "album_name"
        case artistNames = "artist_names"
        case spotifyData = "spotify_data"
    }

    var subtitle: String { artistNames ?? albumName ?? "Juke catalog" }
    var artworkURL: URL? { spotifyData?.images?.first.flatMap(URL.init(string:)) }
}

actor CatalogClient {
    private struct Page: Decodable { let results: [CatalogSearchResult] }
    private let baseURL = URL(string: "https://neptune.tail647b75.ts.net/api/v1/")!

    func search(_ query: String, kind: String, token: String) async throws -> [CatalogSearchResult] {
        var components = URLComponents(url: baseURL.appending(path: "\(kind)/"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "external", value: "true"), URLQueryItem(name: "q", value: query)]
        var request = URLRequest(url: components.url!)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.timeoutInterval = 20
        let (data, response) = try await URLSession.shared.data(for: request)
        guard data.count <= 3_000_000, let http = response as? HTTPURLResponse, http.statusCode == 200 else { throw NeptuneVibeError.invalidResponse }
        if let page = try? JSONDecoder().decode(Page.self, from: data) { return page.results }
        return try JSONDecoder().decode([CatalogSearchResult].self, from: data)
    }
}
