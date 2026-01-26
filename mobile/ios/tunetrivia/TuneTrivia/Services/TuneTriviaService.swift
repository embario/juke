//
//  TuneTriviaService.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-23.
//

import Foundation

final class TuneTriviaService {
    private let client: APIClient
    private let encoder: JSONEncoder

    init(client: APIClient = .shared) {
        self.client = client
        self.encoder = JSONEncoder()
        self.encoder.keyEncodingStrategy = .convertToSnakeCase
    }

    // MARK: - Sessions

    func createSession(
        name: String,
        mode: SessionMode,
        maxSongs: Int,
        secondsPerSong: Int,
        enableTrivia: Bool,
        autoSelectDecade: String? = nil,
        autoSelectGenre: String? = nil,
        autoSelectArtist: String? = nil,
        token: String
    ) async throws -> SessionDetailResponse {
        let request = CreateSessionRequest(
            name: name,
            mode: mode.rawValue,
            maxSongs: maxSongs,
            secondsPerSong: secondsPerSong,
            enableTrivia: enableTrivia,
            autoSelectDecade: autoSelectDecade,
            autoSelectGenre: autoSelectGenre,
            autoSelectArtist: autoSelectArtist
        )
        let bodyData = try encoder.encode(request)
        return try await client.send(
            "/api/v1/tunetrivia/sessions/",
            method: .post,
            token: token,
            body: bodyData
        )
    }

    func joinSession(code: String, displayName: String? = nil, token: String?) async throws -> SessionDetailResponse {
        let request = JoinSessionRequest(code: code, displayName: displayName)
        let bodyData = try encoder.encode(request)
        return try await client.send(
            "/api/v1/tunetrivia/sessions/join/",
            method: .post,
            token: token,
            body: bodyData
        )
    }

    func getSession(id: Int, token: String?) async throws -> SessionDetailResponse {
        return try await client.send(
            "/api/v1/tunetrivia/sessions/\(id)/",
            method: .get,
            token: token
        )
    }

    func getMySessions(token: String) async throws -> [TuneTriviaSession] {
        return try await client.send(
            "/api/v1/tunetrivia/sessions/mine/",
            method: .get,
            token: token
        )
    }

    // MARK: - Game Control

    func startGame(sessionId: Int, token: String) async throws -> SessionDetailResponse {
        return try await client.send(
            "/api/v1/tunetrivia/sessions/\(sessionId)/start/",
            method: .post,
            token: token
        )
    }

    func pauseGame(sessionId: Int, token: String) async throws -> TuneTriviaSession {
        return try await client.send(
            "/api/v1/tunetrivia/sessions/\(sessionId)/pause/",
            method: .post,
            token: token
        )
    }

    func resumeGame(sessionId: Int, token: String) async throws -> TuneTriviaSession {
        return try await client.send(
            "/api/v1/tunetrivia/sessions/\(sessionId)/resume/",
            method: .post,
            token: token
        )
    }

    func endGame(sessionId: Int, token: String) async throws -> TuneTriviaSession {
        return try await client.send(
            "/api/v1/tunetrivia/sessions/\(sessionId)/end/",
            method: .post,
            token: token
        )
    }

    func nextRound(sessionId: Int, token: String) async throws -> TuneTriviaRound {
        return try await client.send(
            "/api/v1/tunetrivia/sessions/\(sessionId)/next-round/",
            method: .post,
            token: token
        )
    }

    func revealRound(sessionId: Int, token: String) async throws -> TuneTriviaRound {
        return try await client.send(
            "/api/v1/tunetrivia/sessions/\(sessionId)/reveal/",
            method: .post,
            token: token
        )
    }

    // MARK: - Tracks

    func addTrack(sessionId: Int, trackId: String, token: String) async throws -> TuneTriviaRound {
        let request = AddTrackRequest(trackId: trackId)
        let bodyData = try encoder.encode(request)
        return try await client.send(
            "/api/v1/tunetrivia/sessions/\(sessionId)/tracks/",
            method: .post,
            token: token,
            body: bodyData
        )
    }

    func autoSelectTracks(sessionId: Int, count: Int, token: String) async throws -> [TuneTriviaRound] {
        return try await client.send(
            "/api/v1/tunetrivia/sessions/\(sessionId)/auto-select/",
            method: .post,
            token: token,
            queryItems: [URLQueryItem(name: "count", value: String(count))]
        )
    }

    func searchTracks(query: String, token: String) async throws -> [SpotifyTrack] {
        return try await client.send(
            "/api/v1/tunetrivia/sessions/search-tracks/",
            method: .get,
            token: token,
            queryItems: [URLQueryItem(name: "q", value: query)]
        )
    }

    // MARK: - Guesses

    func submitGuess(
        roundId: Int,
        songGuess: String?,
        artistGuess: String?,
        token: String?
    ) async throws -> TuneTriviaGuess {
        let request = SubmitGuessRequest(songGuess: songGuess, artistGuess: artistGuess)
        let bodyData = try encoder.encode(request)
        return try await client.send(
            "/api/v1/tunetrivia/rounds/\(roundId)/guess/",
            method: .post,
            token: token,
            body: bodyData
        )
    }

    func getRoundGuesses(roundId: Int, token: String?) async throws -> [TuneTriviaGuess] {
        return try await client.send(
            "/api/v1/tunetrivia/rounds/\(roundId)/guesses/",
            method: .get,
            token: token
        )
    }

    func submitTriviaAnswer(roundId: Int, triviaGuess: String, token: String?) async throws -> TriviaSubmitResponse {
        let request = SubmitTriviaRequest(triviaGuess: triviaGuess)
        let bodyData = try encoder.encode(request)
        return try await client.send(
            "/api/v1/tunetrivia/rounds/\(roundId)/trivia/",
            method: .post,
            token: token,
            body: bodyData
        )
    }

    // MARK: - Players (Host Mode)

    func addManualPlayer(sessionId: Int, displayName: String, token: String) async throws -> TuneTriviaPlayer {
        struct AddPlayerRequest: Encodable {
            let displayName: String
            enum CodingKeys: String, CodingKey {
                case displayName = "display_name"
            }
        }
        let bodyData = try encoder.encode(AddPlayerRequest(displayName: displayName))
        return try await client.send(
            "/api/v1/tunetrivia/sessions/\(sessionId)/players/",
            method: .post,
            token: token,
            body: bodyData
        )
    }

    func awardPoints(playerId: Int, points: Int, token: String) async throws -> TuneTriviaPlayer {
        struct AwardPointsRequest: Encodable {
            let points: Int
        }
        let bodyData = try encoder.encode(AwardPointsRequest(points: points))
        return try await client.send(
            "/api/v1/tunetrivia/players/\(playerId)/award/",
            method: .post,
            token: token,
            body: bodyData
        )
    }

    // MARK: - Leaderboard

    func getLeaderboard(limit: Int = 50) async throws -> [LeaderboardEntry] {
        return try await client.send(
            "/api/v1/tunetrivia/leaderboard/?limit=\(limit)",
            method: .get,
            token: nil
        )
    }
}
