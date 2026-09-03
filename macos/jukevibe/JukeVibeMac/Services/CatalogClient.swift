import Foundation

enum CatalogSearchError: LocalizedError {
    case authenticationExpired
    case invalidResponse
    case serviceUnavailable(Int)

    var errorDescription: String? {
        switch self {
        case .authenticationExpired:
            "Your Juke session has expired. Sign out and sign in again to search."
        case .invalidResponse:
            "Juke returned an unexpected catalog response."
        case .serviceUnavailable(let status):
            "Juke catalog search is unavailable right now (HTTP \(status))."
        }
    }
}

struct CatalogSearchResult: Decodable, Identifiable, Sendable {
    let pk: Int
    let name: String
    let spotifyID: String?
    let albumName: String?
    let artistNames: String?
    let durationMs: Int?
    let albumLink: URL?
    let spotifyData: SpotifyData?

    var id: Int { pk }
    struct SpotifyData: Decodable, Sendable {
        let images: [String]?
        let uri: String?
    }

    enum CodingKeys: String, CodingKey {
        case pk, name
        case spotifyID = "spotify_id"
        case albumName = "album_name"
        case artistNames = "artist_names"
        case durationMs = "duration_ms"
        case albumLink = "album_link"
        case spotifyData = "spotify_data"
    }

    var subtitle: String { artistNames ?? albumName ?? "Juke catalog" }
    var artworkURL: URL? { spotifyData?.images?.first.flatMap(URL.init(string:)) }
    var recognizedTrack: RecognizedTrack {
        RecognizedTrack(
            title: name,
            artist: artistNames ?? "Unknown artist",
            album: albumName,
            isrc: nil,
            artworkURL: artworkURL,
            appleMusicURL: nil,
            shazamID: nil,
            trackDuration: durationMs.map { TimeInterval($0) / 1_000 },
            providerNamespace: "spotify",
            providerTrackID: spotifyID,
            providerPlaybackURL: spotifyID.flatMap { URL(string: "spotify:track:\($0)") }
        )
    }
}

actor CatalogClient {
    private struct Page: Decodable { let results: [CatalogSearchResult] }
    private let baseURL = URL(string: "https://neptune.tail647b75.ts.net/api/v1/")!
    private let usesFixtures = ProcessInfo.processInfo.arguments.contains("--uitesting")

    func search(_ query: String, kind: String, token: String) async throws -> [CatalogSearchResult] {
        if usesFixtures {
            try await Task.sleep(for: .milliseconds(250))
            return [CatalogSearchResult(
                pk: 1959,
                name: "Blue in Green",
                spotifyID: "0aWMVrwxPNYkKmFthzmpRi",
                albumName: "Kind of Blue",
                artistNames: "Miles Davis",
                durationMs: 327_000,
                albumLink: nil,
                spotifyData: nil
            )]
        }

        var components = URLComponents(url: baseURL.appending(path: kind).appendingPathComponent(""), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "external", value: "true"), URLQueryItem(name: "q", value: query)]
        var request = Self.authorizedRequest(url: components.url!, token: token)
        request.timeoutInterval = 20
        let (data, response) = try await URLSession.shared.data(for: request)
        guard data.count <= 3_000_000, let http = response as? HTTPURLResponse else {
            throw CatalogSearchError.invalidResponse
        }
        if http.statusCode == 401 { throw CatalogSearchError.authenticationExpired }
        guard http.statusCode == 200 else { throw CatalogSearchError.serviceUnavailable(http.statusCode) }
        if let page = try? JSONDecoder().decode(Page.self, from: data) { return page.results }
        do { return try JSONDecoder().decode([CatalogSearchResult].self, from: data) }
        catch { throw CatalogSearchError.invalidResponse }
    }

    func artwork(for result: CatalogSearchResult, token: String) async -> URL? {
        if let artworkURL = result.artworkURL { return artworkURL }
        guard let albumLink = result.albumLink,
              albumLink.scheme == "https",
              albumLink.host == baseURL.host else { return nil }
        var request = Self.authorizedRequest(url: albumLink, token: token)
        request.timeoutInterval = 8
        guard let (data, response) = try? await URLSession.shared.data(for: request),
              data.count <= 1_048_576,
              let http = response as? HTTPURLResponse,
              http.statusCode == 200,
              let album = try? JSONDecoder().decode(AlbumArtwork.self, from: data) else { return nil }
        return album.spotifyData?.images?.first.flatMap(URL.init(string:))
    }

    nonisolated static func authorizedRequest(url: URL, token: String) -> URLRequest {
        var request = URLRequest(url: url)
        request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        return request
    }
}

private struct AlbumArtwork: Decodable {
    let spotifyData: CatalogSearchResult.SpotifyData?

    enum CodingKeys: String, CodingKey {
        case spotifyData = "spotify_data"
    }
}
