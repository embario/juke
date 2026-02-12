//
//  TuneTriviaService.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-23.
//

import Foundation
import JukeCore

final class TuneTriviaService {
    private let client: JukeAPIClient

    init(client: JukeAPIClient = .shared) {
        self.client = client
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
        return try await client.post(
            "/api/v1/tunetrivia/sessions/",
            body: request,
            token: token
        )
    }

    func joinSession(code: String, displayName: String? = nil, token: String?) async throws -> SessionDetailResponse {
        let request = JoinSessionRequest(code: code, displayName: displayName)
        return try await client.post(
            "/api/v1/tunetrivia/sessions/join/",
            body: request,
            token: token
        )
    }

    func getSession(id: Int, token: String?) async throws -> SessionDetailResponse {
        return try await client.get(
            "/api/v1/tunetrivia/sessions/\(id)/",
            token: token
        )
    }

    func getMySessions(token: String) async throws -> [TuneTriviaSession] {
        return try await client.get(
            "/api/v1/tunetrivia/sessions/mine/",
            token: token
        )
    }

    // MARK: - Game Control

    func startGame(sessionId: Int, token: String) async throws -> SessionDetailResponse {
        return try await client.post(
            "/api/v1/tunetrivia/sessions/\(sessionId)/start/",
            body: nil as String?,
            token: token
        )
    }

    func pauseGame(sessionId: Int, token: String) async throws -> TuneTriviaSession {
        return try await client.post(
            "/api/v1/tunetrivia/sessions/\(sessionId)/pause/",
            body: nil as String?,
            token: token
        )
    }

    func resumeGame(sessionId: Int, token: String) async throws -> TuneTriviaSession {
        return try await client.post(
            "/api/v1/tunetrivia/sessions/\(sessionId)/resume/",
            body: nil as String?,
            token: token
        )
    }

    func endGame(sessionId: Int, token: String) async throws -> TuneTriviaSession {
        return try await client.post(
            "/api/v1/tunetrivia/sessions/\(sessionId)/end/",
            body: nil as String?,
            token: token
        )
    }

    func nextRound(sessionId: Int, token: String) async throws -> TuneTriviaRound {
        return try await client.post(
            "/api/v1/tunetrivia/sessions/\(sessionId)/next-round/",
            body: nil as String?,
            token: token
        )
    }

    func revealRound(sessionId: Int, token: String) async throws -> TuneTriviaRound {
        return try await client.post(
            "/api/v1/tunetrivia/sessions/\(sessionId)/reveal/",
            body: nil as String?,
            token: token
        )
    }

    // MARK: - Tracks

    func addTrack(sessionId: Int, trackId: String, token: String) async throws -> TuneTriviaRound {
        let request = AddTrackRequest(trackId: trackId)
        return try await client.post(
            "/api/v1/tunetrivia/sessions/\(sessionId)/tracks/",
            body: request,
            token: token
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
        return try await client.get(
            "/api/v1/tunetrivia/sessions/search-tracks/",
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
        return try await client.post(
            "/api/v1/tunetrivia/rounds/\(roundId)/guess/",
            body: request,
            token: token
        )
    }

    func getRoundGuesses(roundId: Int, token: String?) async throws -> [TuneTriviaGuess] {
        return try await client.get(
            "/api/v1/tunetrivia/rounds/\(roundId)/guesses/",
            token: token
        )
    }

    func submitTriviaAnswer(roundId: Int, triviaGuess: String, token: String?) async throws -> TriviaSubmitResponse {
        let request = SubmitTriviaRequest(triviaGuess: triviaGuess)
        return try await client.post(
            "/api/v1/tunetrivia/rounds/\(roundId)/trivia/",
            body: request,
            token: token
        )
    }

    // MARK: - Players (Host Mode)

    func addManualPlayer(sessionId: Int, displayName: String, token: String) async throws -> TuneTriviaPlayer {
        struct AddPlayerRequest: Encodable {
            let displayName: String
        }
        return try await client.post(
            "/api/v1/tunetrivia/sessions/\(sessionId)/players/",
            body: AddPlayerRequest(displayName: displayName),
            token: token
        )
    }

    func awardPoints(playerId: Int, points: Int, token: String) async throws -> TuneTriviaPlayer {
        struct AwardPointsRequest: Encodable {
            let points: Int
        }
        return try await client.post(
            "/api/v1/tunetrivia/players/\(playerId)/award/",
            body: AwardPointsRequest(points: points),
            token: token
        )
    }

    // MARK: - Leaderboard

    func getLeaderboard(limit: Int = 50) async throws -> [LeaderboardEntry] {
        return try await client.get(
            "/api/v1/tunetrivia/leaderboard/?limit=\(limit)",
            token: nil
        )
    }
}
