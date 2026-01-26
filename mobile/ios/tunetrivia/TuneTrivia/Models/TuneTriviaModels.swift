//
//  TuneTriviaModels.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-23.
//

import Foundation

// MARK: - Session

struct TuneTriviaSession: Codable, Identifiable {
    let id: Int
    let code: String
    let name: String
    let hostUsername: String
    let mode: SessionMode
    let status: SessionStatus
    let maxSongs: Int
    let secondsPerSong: Int
    let enableTrivia: Bool
    let playerCount: Int?
    let roundCount: Int?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, code, name, mode, status
        case hostUsername = "host_username"
        case maxSongs = "max_songs"
        case secondsPerSong = "seconds_per_song"
        case enableTrivia = "enable_trivia"
        case playerCount = "player_count"
        case roundCount = "round_count"
        case createdAt = "created_at"
    }
}

enum SessionMode: String, Codable, CaseIterable {
    case host = "host"
    case party = "party"

    var displayName: String {
        switch self {
        case .host: return "Host Mode"
        case .party: return "Party Mode"
        }
    }

    var description: String {
        switch self {
        case .host: return "You control scoring manually"
        case .party: return "Players score themselves with codes"
        }
    }
}

enum SessionStatus: String, Codable {
    case lobby = "lobby"
    case playing = "playing"
    case paused = "paused"
    case finished = "finished"
}

// MARK: - Player

struct TuneTriviaPlayer: Codable, Identifiable {
    let id: Int
    let displayName: String
    let isHost: Bool
    let totalScore: Int
    let joinedAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case displayName = "display_name"
        case isHost = "is_host"
        case totalScore = "total_score"
        case joinedAt = "joined_at"
    }
}

// MARK: - Round

struct TuneTriviaRound: Codable, Identifiable {
    let id: Int
    let roundNumber: Int
    let status: RoundStatus
    let trackName: String
    let artistName: String
    let albumName: String?
    let albumArtUrl: String?
    let previewUrl: String?
    let triviaQuestion: String?
    let triviaOptions: [String]?
    let triviaAnswer: String?
    let startedAt: String?
    let revealedAt: String?

    /// Whether this round has a trivia question available.
    var hasTrivia: Bool {
        triviaQuestion != nil && triviaOptions != nil && (triviaOptions?.count ?? 0) == 4
    }

    enum CodingKeys: String, CodingKey {
        case id
        case roundNumber = "round_number"
        case status
        case trackName = "track_name"
        case artistName = "artist_name"
        case albumName = "album_name"
        case albumArtUrl = "album_art_url"
        case previewUrl = "preview_url"
        case triviaQuestion = "trivia_question"
        case triviaOptions = "trivia_options"
        case triviaAnswer = "trivia_answer"
        case startedAt = "started_at"
        case revealedAt = "revealed_at"
    }
}

enum RoundStatus: String, Codable {
    case pending = "pending"
    case playing = "playing"
    case revealed = "revealed"
    case finished = "finished"
}

// MARK: - Guess

struct TuneTriviaGuess: Codable, Identifiable {
    let id: Int
    let player: Int
    let playerName: String
    let songGuess: String?
    let artistGuess: String?
    let triviaGuess: String?
    let songCorrect: Bool
    let artistCorrect: Bool
    let triviaCorrect: Bool
    let pointsEarned: Int
    let submittedAt: String

    enum CodingKeys: String, CodingKey {
        case id, player
        case playerName = "player_name"
        case songGuess = "song_guess"
        case artistGuess = "artist_guess"
        case triviaGuess = "trivia_guess"
        case songCorrect = "song_correct"
        case artistCorrect = "artist_correct"
        case triviaCorrect = "trivia_correct"
        case pointsEarned = "points_earned"
        case submittedAt = "submitted_at"
    }
}

// MARK: - Leaderboard

struct LeaderboardEntry: Codable, Identifiable {
    let id: Int
    let displayName: String
    let totalScore: Int
    let totalGames: Int
    let totalCorrectSongs: Int
    let totalCorrectArtists: Int
    let totalCorrectTrivia: Int
    let lastPlayedAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case displayName = "display_name"
        case totalScore = "total_score"
        case totalGames = "total_games"
        case totalCorrectSongs = "total_correct_songs"
        case totalCorrectArtists = "total_correct_artists"
        case totalCorrectTrivia = "total_correct_trivia"
        case lastPlayedAt = "last_played_at"
    }
}

// MARK: - API Request/Response Models

struct CreateSessionRequest: Encodable {
    let name: String
    let mode: String
    let maxSongs: Int
    let secondsPerSong: Int
    let enableTrivia: Bool
    let autoSelectDecade: String?
    let autoSelectGenre: String?
    let autoSelectArtist: String?

    enum CodingKeys: String, CodingKey {
        case name, mode
        case maxSongs = "max_songs"
        case secondsPerSong = "seconds_per_song"
        case enableTrivia = "enable_trivia"
        case autoSelectDecade = "auto_select_decade"
        case autoSelectGenre = "auto_select_genre"
        case autoSelectArtist = "auto_select_artist"
    }
}

struct JoinSessionRequest: Encodable {
    let code: String
    let displayName: String?

    enum CodingKeys: String, CodingKey {
        case code
        case displayName = "display_name"
    }
}

struct SubmitGuessRequest: Encodable {
    let songGuess: String?
    let artistGuess: String?

    enum CodingKeys: String, CodingKey {
        case songGuess = "song_guess"
        case artistGuess = "artist_guess"
    }
}

struct AddTrackRequest: Encodable {
    let trackId: String

    enum CodingKeys: String, CodingKey {
        case trackId = "track_id"
    }
}

struct SubmitTriviaRequest: Encodable {
    let triviaGuess: String

    enum CodingKeys: String, CodingKey {
        case triviaGuess = "trivia_guess"
    }
}

struct TriviaSubmitResponse: Codable {
    let correct: Bool
    let correctAnswer: String
    let pointsEarned: Int
    let totalScore: Int

    enum CodingKeys: String, CodingKey {
        case correct
        case correctAnswer = "correct_answer"
        case pointsEarned = "points_earned"
        case totalScore = "total_score"
    }
}

/// Response for session detail - backend returns flat structure with players/rounds at top level
struct SessionDetailResponse: Codable {
    let id: Int
    let code: String
    let name: String
    let hostUsername: String
    let mode: SessionMode
    let status: SessionStatus
    let maxSongs: Int
    let secondsPerSong: Int
    let enableTrivia: Bool
    let playerCount: Int?
    let roundCount: Int?
    let createdAt: String
    let players: [TuneTriviaPlayer]
    let rounds: [TuneTriviaRound]

    enum CodingKeys: String, CodingKey {
        case id, code, name, mode, status, players, rounds
        case hostUsername = "host_username"
        case maxSongs = "max_songs"
        case secondsPerSong = "seconds_per_song"
        case enableTrivia = "enable_trivia"
        case playerCount = "player_count"
        case roundCount = "round_count"
        case createdAt = "created_at"
    }

    /// Convert to TuneTriviaSession for compatibility
    var session: TuneTriviaSession {
        TuneTriviaSession(
            id: id,
            code: code,
            name: name,
            hostUsername: hostUsername,
            mode: mode,
            status: status,
            maxSongs: maxSongs,
            secondsPerSong: secondsPerSong,
            enableTrivia: enableTrivia,
            playerCount: playerCount,
            roundCount: roundCount,
            createdAt: createdAt
        )
    }
}
