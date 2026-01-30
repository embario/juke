import Foundation

final class OnboardingService {
    private let client: APIClient

    init(client: APIClient = .shared) {
        self.client = client
    }

    func fetchFeaturedGenres(token: String) async throws -> [OnboardingGenre] {
        let response: [OnboardingGenre] = try await client.send(
            "/api/v1/genres/featured/",
            token: token
        )
        return response
    }

    // Search artists via the catalog endpoint
    func searchArtists(query: String, token: String) async throws -> [OnboardingArtist] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return [] }

        struct ArtistSearchResult: Decodable {
            let pk: Int
            let name: String
            let spotifyId: String
            let spotifyData: SpotifyData?

            enum CodingKeys: String, CodingKey {
                case pk, name
                case spotifyId = "spotify_id"
                case spotifyData = "spotify_data"
            }
        }

        struct SpotifyData: Decodable {
            let images: [String]?
        }

        struct ArtistsResponse: Decodable {
            let results: [ArtistSearchResult]

            private enum CodingKeys: String, CodingKey {
                case results
            }

            init(from decoder: Decoder) throws {
                if let container = try? decoder.container(keyedBy: CodingKeys.self),
                   let wrapped = try? container.decode([ArtistSearchResult].self, forKey: .results) {
                    results = wrapped
                    return
                }
                let single = try decoder.singleValueContainer()
                results = try single.decode([ArtistSearchResult].self)
            }
        }

        let queryItems = [
            URLQueryItem(name: "external", value: "true"),
            URLQueryItem(name: "q", value: trimmed),
        ]

        let response: ArtistsResponse = try await client.send(
            "/api/v1/artists/",
            token: token,
            queryItems: queryItems
        )

        return response.results.prefix(10).map { result in
            OnboardingArtist(
                id: String(result.pk),
                name: result.name,
                spotifyId: result.spotifyId,
                imageUrl: result.spotifyData?.images?.first ?? "",
                genres: []
            )
        }
    }

    // Save onboarding profile data
    func saveProfile(data: OnboardingData, token: String) async throws {
        struct ProfilePayload: Encodable {
            let favoriteGenres: [String]
            let favoriteArtists: [String]
            let location: String
            let cityLat: Double?
            let cityLng: Double?
            let onboardingCompletedAt: String
            let customData: CustomData

            enum CodingKeys: String, CodingKey {
                case favoriteGenres = "favorite_genres"
                case favoriteArtists = "favorite_artists"
                case location
                case cityLat = "city_lat"
                case cityLng = "city_lng"
                case onboardingCompletedAt = "onboarding_completed_at"
                case customData = "custom_data"
            }
        }

        struct CustomData: Encodable {
            let hatedGenres: [String]
            let rainyDayMood: String?
            let workoutVibe: String?
            let favoriteDecade: String?
            let listeningStyle: String?
            let ageRange: String?

            enum CodingKeys: String, CodingKey {
                case hatedGenres = "hated_genres"
                case rainyDayMood = "rainy_day_mood"
                case workoutVibe = "workout_vibe"
                case favoriteDecade = "favorite_decade"
                case listeningStyle = "listening_style"
                case ageRange = "age_range"
            }
        }

        let completedAt = ISO8601DateFormatter().string(from: Date())
        let payload = ProfilePayload(
            favoriteGenres: data.favoriteGenres,
            favoriteArtists: data.rideOrDieArtist.map { [$0.spotifyId] } ?? [],
            location: data.location?.name ?? "",
            cityLat: data.location?.lat,
            cityLng: data.location?.lng,
            onboardingCompletedAt: completedAt,
            customData: CustomData(
                hatedGenres: data.hatedGenres,
                rainyDayMood: data.rainyDayMood,
                workoutVibe: data.workoutVibe,
                favoriteDecade: data.favoriteDecade,
                listeningStyle: data.listeningStyle,
                ageRange: data.ageRange
            )
        )

        let encoder = JSONEncoder()
        let body = try encoder.encode(payload)

        let _: EmptyResponse = try await client.send(
            "/api/v1/music-profiles/me/",
            method: .patch,
            token: token,
            body: body
        )
    }
}
