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
    let artworkURL: URL?
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
        case artworkURL = "artwork_url"
        case spotifyData = "spotify_data"
    }

    var subtitle: String { artistNames ?? albumName ?? "Juke catalog" }
    var resolvedArtworkURL: URL? { artworkURL ?? spotifyData?.images?.first.flatMap(URL.init(string:)) }
    var albumPK: Int? { albumLink?.pathComponents.reversed().compactMap(Int.init).first }
    func spotifyURL(kind: String) -> URL? {
        guard let spotifyID else { return nil }
        let resource = kind == "artists" ? "artist" : kind == "albums" ? "album" : "track"
        return URL(string: "https://open.spotify.com/\(resource)/\(spotifyID)")
    }
    var recognizedTrack: RecognizedTrack {
        RecognizedTrack(
            title: name,
            artist: artistNames ?? "Unknown artist",
            album: albumName,
            isrc: nil,
            artworkURL: resolvedArtworkURL,
            appleMusicURL: nil,
            shazamID: nil,
            trackDuration: durationMs.map { TimeInterval($0) / 1_000 },
            providerNamespace: "spotify",
            providerTrackID: spotifyID,
            providerPlaybackURL: spotifyID.flatMap { URL(string: "spotify:track:\($0)") }
        )
    }
}

struct CatalogTrackDetail: Decodable, Identifiable, Sendable {
    let pk: Int
    let name: String
    let spotifyID: String?
    let durationMs: Int?
    let trackNumber: Int?
    let discNumber: Int?

    var id: Int { pk }

    enum CodingKeys: String, CodingKey {
        case pk, name
        case spotifyID = "spotify_id"
        case durationMs = "duration_ms"
        case trackNumber = "track_number"
        case discNumber = "disc_number"
    }
}

struct CatalogAlbumSummary: Decodable, Identifiable, Sendable {
    let pk: Int
    let name: String
    let spotifyID: String?
    let spotifyData: CatalogSearchResult.SpotifyData?
    let totalTracks: Int?
    let releaseDate: String?

    var id: Int { pk }
    var artworkURL: URL? { spotifyData?.images?.first.flatMap(URL.init(string:)) }

    enum CodingKeys: String, CodingKey {
        case pk, name
        case spotifyID = "spotify_id"
        case spotifyData = "spotify_data"
        case totalTracks = "total_tracks"
        case releaseDate = "release_date"
    }
}

struct CatalogAlbumDetail: Decodable, Identifiable, Sendable {
    let pk: Int
    let name: String
    let spotifyID: String?
    let spotifyData: CatalogSearchResult.SpotifyData?
    let description: String?
    let albumType: String?
    let totalTracks: Int?
    let releaseDate: String?
    let tracks: [CatalogTrackDetail]
    let relatedAlbums: [CatalogAlbumSummary]

    var id: Int { pk }
    var artworkURL: URL? { spotifyData?.images?.first.flatMap(URL.init(string:)) }
    var spotifyURL: URL? { spotifyID.flatMap { URL(string: "https://open.spotify.com/album/\($0)") } }

    enum CodingKeys: String, CodingKey {
        case pk, name, description, tracks
        case spotifyID = "spotify_id"
        case spotifyData = "spotify_data"
        case albumType = "album_type"
        case totalTracks = "total_tracks"
        case releaseDate = "release_date"
        case relatedAlbums = "related_albums"
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        pk = try values.decode(Int.self, forKey: .pk)
        name = try values.decode(String.self, forKey: .name)
        spotifyID = try values.decodeIfPresent(String.self, forKey: .spotifyID)
        spotifyData = try values.decodeIfPresent(CatalogSearchResult.SpotifyData.self, forKey: .spotifyData)
        description = try values.decodeIfPresent(String.self, forKey: .description)
        albumType = try values.decodeIfPresent(String.self, forKey: .albumType)
        totalTracks = try values.decodeIfPresent(Int.self, forKey: .totalTracks)
        releaseDate = try values.decodeIfPresent(String.self, forKey: .releaseDate)
        tracks = try values.decodeIfPresent([CatalogTrackDetail].self, forKey: .tracks) ?? []
        relatedAlbums = try values.decodeIfPresent([CatalogAlbumSummary].self, forKey: .relatedAlbums) ?? []
    }
}

struct CatalogArtistSummary: Decodable, Identifiable, Sendable {
    let pk: Int
    let name: String
    let spotifyData: CatalogSearchResult.SpotifyData?

    var id: Int { pk }
    var artworkURL: URL? { spotifyData?.images?.first.flatMap(URL.init(string:)) }

    enum CodingKeys: String, CodingKey {
        case pk, name
        case spotifyData = "spotify_data"
    }
}

struct CatalogNamedResource: Decodable, Identifiable, Sendable {
    let pk: Int
    let name: String
    var id: Int { pk }
}

struct CatalogArtistDetail: Decodable, Identifiable, Sendable {
    let pk: Int
    let name: String
    let spotifyID: String?
    let spotifyData: CatalogSearchResult.SpotifyData?
    let bio: String?
    let genres: [CatalogNamedResource]
    let albums: [CatalogAlbumSummary]
    let topTracks: [CatalogTrackDetail]
    let relatedArtists: [CatalogArtistSummary]

    var id: Int { pk }
    var artworkURL: URL? { spotifyData?.images?.first.flatMap(URL.init(string:)) }
    var spotifyURL: URL? { spotifyID.flatMap { URL(string: "https://open.spotify.com/artist/\($0)") } }

    enum CodingKeys: String, CodingKey {
        case pk, name, bio, genres, albums
        case spotifyID = "spotify_id"
        case spotifyData = "spotify_data"
        case topTracks = "top_tracks"
        case relatedArtists = "related_artists"
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        pk = try values.decode(Int.self, forKey: .pk)
        name = try values.decode(String.self, forKey: .name)
        spotifyID = try values.decodeIfPresent(String.self, forKey: .spotifyID)
        spotifyData = try values.decodeIfPresent(CatalogSearchResult.SpotifyData.self, forKey: .spotifyData)
        bio = try values.decodeIfPresent(String.self, forKey: .bio)
        genres = try values.decodeIfPresent([CatalogNamedResource].self, forKey: .genres) ?? []
        albums = try values.decodeIfPresent([CatalogAlbumSummary].self, forKey: .albums) ?? []
        topTracks = try values.decodeIfPresent([CatalogTrackDetail].self, forKey: .topTracks) ?? []
        relatedArtists = try values.decodeIfPresent([CatalogArtistSummary].self, forKey: .relatedArtists) ?? []
    }
}

actor CatalogClient {
    private struct Page: Decodable { let results: [CatalogSearchResult] }
    private struct SpotifyOEmbed: Decodable {
        let thumbnailURL: URL?

        enum CodingKeys: String, CodingKey {
            case thumbnailURL = "thumbnail_url"
        }
    }
    private var baseURL: URL { JukeServer.apiURL() }
    private let usesFixtures = ProcessInfo.processInfo.arguments.contains("--uitesting")

    func search(_ query: String, kind: String, token: String) async throws -> [CatalogSearchResult] {
        if usesFixtures {
            try await Task.sleep(for: .milliseconds(250))
            if kind == "artists" {
                return [CatalogSearchResult(
                    pk: 26,
                    name: "Miles Davis",
                    spotifyID: "0kbYTNQb4Pb1rPbbaF0pT4",
                    albumName: nil,
                    artistNames: nil,
                    durationMs: nil,
                    albumLink: nil,
                    artworkURL: URL(string: "https://i.scdn.co/image/example-artist"),
                    spotifyData: nil
                )]
            }
            if kind == "albums" {
                return [CatalogSearchResult(
                    pk: 1959,
                    name: "Kind of Blue",
                    spotifyID: "1weenld61qoidwYuZ1GESA",
                    albumName: nil,
                    artistNames: "Miles Davis",
                    durationMs: nil,
                    albumLink: nil,
                    artworkURL: URL(string: "https://i.scdn.co/image/example-album"),
                    spotifyData: nil
                )]
            }
            return [CatalogSearchResult(
                pk: 1959,
                name: "Blue in Green",
                spotifyID: "0aWMVrwxPNYkKmFthzmpRi",
                albumName: "Kind of Blue",
                artistNames: "Miles Davis",
                durationMs: 327_000,
                albumLink: JukeServer.apiURL().appending(path: "albums/1959/"),
                artworkURL: URL(string: "https://i.scdn.co/image/example"),
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

    func album(id: Int, token: String) async throws -> CatalogAlbumDetail {
        if usesFixtures { return try Self.fixtureAlbum() }
        return try await detail(url: baseURL.appending(path: "albums/\(id)/"), token: token)
    }

    func album(for result: CatalogSearchResult, token: String) async throws -> CatalogAlbumDetail {
        if let albumPK = result.albumPK { return try await album(id: albumPK, token: token) }
        guard let albumName = result.albumName else { throw CatalogSearchError.invalidResponse }
        guard let match = try await search(albumName, kind: "albums", token: token).first else {
            throw CatalogSearchError.invalidResponse
        }
        return try await album(id: match.pk, token: token)
    }

    func artist(id: Int, token: String) async throws -> CatalogArtistDetail {
        if usesFixtures { return try Self.fixtureArtist() }
        return try await detail(url: baseURL.appending(path: "artists/\(id)/"), token: token)
    }

    private func detail<T: Decodable>(url: URL, token: String) async throws -> T {
        var request = Self.authorizedRequest(url: url, token: token)
        request.timeoutInterval = 20
        let (data, response) = try await URLSession.shared.data(for: request)
        guard data.count <= 3_000_000, let http = response as? HTTPURLResponse else {
            throw CatalogSearchError.invalidResponse
        }
        if http.statusCode == 401 { throw CatalogSearchError.authenticationExpired }
        guard http.statusCode == 200 else { throw CatalogSearchError.serviceUnavailable(http.statusCode) }
        do { return try JSONDecoder().decode(T.self, from: data) }
        catch { throw CatalogSearchError.invalidResponse }
    }

    func artwork(for result: CatalogSearchResult, kind: String = "tracks", token: String) async -> URL? {
        if let artworkURL = result.resolvedArtworkURL { return artworkURL }
        if let albumLink = result.albumLink,
           albumLink.scheme == "https",
           albumLink.host == baseURL.host {
            var request = Self.authorizedRequest(url: albumLink, token: token)
            request.timeoutInterval = 8
            if let (data, response) = try? await URLSession.shared.data(for: request),
               data.count <= 1_048_576,
               let http = response as? HTTPURLResponse,
               http.statusCode == 200,
               let album = try? JSONDecoder().decode(AlbumArtwork.self, from: data),
               let artworkURL = album.spotifyData?.images?.first.flatMap(URL.init(string:)) {
                return artworkURL
            }
        }

        // Older Neptune responses did not preserve the album image embedded in
        // Spotify track search results. Spotify oEmbed supplies the same cover
        // without requiring a user's Spotify account or exposing credentials.
        guard let oEmbedURL = Self.spotifyOEmbedURL(for: result, kind: kind) else { return nil }
        var request = URLRequest(url: oEmbedURL)
        request.timeoutInterval = 8
        guard let (data, response) = try? await URLSession.shared.data(for: request),
              data.count <= 1_048_576,
              let http = response as? HTTPURLResponse,
              http.statusCode == 200 else { return nil }
        return try? JSONDecoder().decode(SpotifyOEmbed.self, from: data).thumbnailURL
    }

    nonisolated static func spotifyOEmbedURL(for result: CatalogSearchResult, kind: String = "tracks") -> URL? {
        let resource = kind == "artists" ? "artist" : kind == "albums" ? "album" : "track"
        let uri = result.spotifyData?.uri ?? result.spotifyID.map { "spotify:\(resource):\($0)" }
        guard let uri, uri.hasPrefix("spotify:") else { return nil }
        var components = URLComponents(string: "https://open.spotify.com/oembed")
        components?.queryItems = [URLQueryItem(name: "url", value: uri)]
        return components?.url
    }

    nonisolated static func authorizedRequest(url: URL, token: String) -> URLRequest {
        var request = URLRequest(url: url)
        request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        return request
    }

    private nonisolated static func fixtureAlbum() throws -> CatalogAlbumDetail {
        try JSONDecoder().decode(CatalogAlbumDetail.self, from: Data(
            """
            {
              "pk":1959,
              "name":"Kind of Blue",
              "spotify_id":"1weenld61qoidwYuZ1GESA",
              "spotify_data":{"images":[],"uri":"spotify:album:1weenld61qoidwYuZ1GESA"},
              "description":"A landmark modal-jazz album built from spacious forms and extraordinary ensemble listening.",
              "album_type":"ALBUM",
              "total_tracks":5,
              "release_date":"1959-08-17",
              "tracks":[
                {"pk":1,"name":"So What","spotify_id":"track-so-what","duration_ms":560000,"track_number":1,"disc_number":1},
                {"pk":2,"name":"Freddie Freeloader","spotify_id":"track-freddie","duration_ms":590000,"track_number":2,"disc_number":1},
                {"pk":3,"name":"Blue in Green","spotify_id":"0aWMVrwxPNYkKmFthzmpRi","duration_ms":327000,"track_number":3,"disc_number":1}
              ],
              "related_albums":[{"pk":1960,"name":"Sketches of Spain","spotify_id":"related-album","spotify_data":{"images":[]},"total_tracks":5,"release_date":"1960-07-18"}]
            }
            """.utf8
        ))
    }

    private nonisolated static func fixtureArtist() throws -> CatalogArtistDetail {
        try JSONDecoder().decode(CatalogArtistDetail.self, from: Data(
            """
            {
              "pk":26,
              "name":"Miles Davis",
              "spotify_id":"0kbYTNQb4Pb1rPbbaF0pT4",
              "spotify_data":{"images":[],"uri":"spotify:artist:0kbYTNQb4Pb1rPbbaF0pT4"},
              "bio":"An American trumpeter, bandleader, and composer whose restless curiosity reshaped modern jazz.",
              "genres":[{"pk":1,"name":"jazz"},{"pk":2,"name":"modal jazz"}],
              "albums":[{"pk":1959,"name":"Kind of Blue","spotify_id":"1weenld61qoidwYuZ1GESA","spotify_data":{"images":[]},"total_tracks":5,"release_date":"1959-08-17"}],
              "top_tracks":[{"pk":3,"name":"Blue in Green","spotify_id":"0aWMVrwxPNYkKmFthzmpRi","duration_ms":327000,"track_number":3,"disc_number":1}],
              "related_artists":[{"pk":27,"name":"John Coltrane","spotify_data":{"images":[]}}]
            }
            """.utf8
        ))
    }
}

private struct AlbumArtwork: Decodable {
    let spotifyData: CatalogSearchResult.SpotifyData?

    enum CodingKeys: String, CodingKey {
        case spotifyData = "spotify_data"
    }
}
