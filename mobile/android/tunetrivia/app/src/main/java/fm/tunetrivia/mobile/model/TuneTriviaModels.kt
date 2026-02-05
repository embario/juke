package fm.tunetrivia.mobile.model

import fm.tunetrivia.mobile.data.network.dto.LeaderboardEntryDto
import fm.tunetrivia.mobile.data.network.dto.SessionDetailResponse
import fm.tunetrivia.mobile.data.network.dto.SpotifyTrackDto
import fm.tunetrivia.mobile.data.network.dto.TuneTriviaGuessDto
import fm.tunetrivia.mobile.data.network.dto.TuneTriviaPlayerDto
import fm.tunetrivia.mobile.data.network.dto.TuneTriviaRoundDto
import fm.tunetrivia.mobile.data.network.dto.TuneTriviaSessionDto
import fm.tunetrivia.mobile.data.network.dto.TriviaSubmitResponse

enum class SessionMode(val raw: String) {
    HOST("host"),
    PARTY("party"),
}

enum class SessionStatus(val raw: String) {
    LOBBY("lobby"),
    PLAYING("playing"),
    PAUSED("paused"),
    FINISHED("finished"),
}

enum class RoundStatus(val raw: String) {
    PENDING("pending"),
    PLAYING("playing"),
    REVEALED("revealed"),
    FINISHED("finished"),
}

data class TuneTriviaSession(
    val id: Int,
    val code: String,
    val name: String,
    val hostUsername: String,
    val mode: SessionMode,
    val status: SessionStatus,
    val maxSongs: Int,
    val secondsPerSong: Int,
    val enableTrivia: Boolean,
    val playerCount: Int?,
    val roundCount: Int?,
    val createdAt: String,
)

data class TuneTriviaPlayer(
    val id: Int,
    val displayName: String,
    val isHost: Boolean,
    val totalScore: Int,
    val joinedAt: String,
)

data class TuneTriviaRound(
    val id: Int,
    val roundNumber: Int,
    val status: RoundStatus,
    val trackName: String,
    val artistName: String,
    val albumName: String?,
    val albumArtUrl: String?,
    val previewUrl: String?,
    val triviaQuestion: String?,
    val triviaOptions: List<String>?,
    val triviaAnswer: String?,
    val startedAt: String?,
    val revealedAt: String?,
) {
    val hasTrivia: Boolean
        get() = triviaQuestion != null && triviaOptions?.size == 4
}

data class TuneTriviaGuess(
    val id: Int,
    val player: Int,
    val playerName: String,
    val songGuess: String?,
    val artistGuess: String?,
    val triviaGuess: String?,
    val songCorrect: Boolean,
    val artistCorrect: Boolean,
    val triviaCorrect: Boolean,
    val pointsEarned: Int,
    val submittedAt: String,
)

data class LeaderboardEntry(
    val id: Int,
    val displayName: String,
    val totalScore: Int,
    val totalGames: Int,
    val totalCorrectSongs: Int,
    val totalCorrectArtists: Int,
    val totalCorrectTrivia: Int,
    val lastPlayedAt: String,
)

data class SpotifyTrack(
    val id: String,
    val name: String,
    val artistName: String,
    val albumName: String,
    val albumArtUrl: String?,
    val previewUrl: String?,
)

data class SessionDetail(
    val id: Int,
    val code: String,
    val name: String,
    val hostUsername: String,
    val mode: SessionMode,
    val status: SessionStatus,
    val maxSongs: Int,
    val secondsPerSong: Int,
    val enableTrivia: Boolean,
    val playerCount: Int?,
    val roundCount: Int?,
    val createdAt: String,
    val players: List<TuneTriviaPlayer>,
    val rounds: List<TuneTriviaRound>,
) {
    val session: TuneTriviaSession
        get() = TuneTriviaSession(
            id = id,
            code = code,
            name = name,
            hostUsername = hostUsername,
            mode = mode,
            status = status,
            maxSongs = maxSongs,
            secondsPerSong = secondsPerSong,
            enableTrivia = enableTrivia,
            playerCount = playerCount,
            roundCount = roundCount,
            createdAt = createdAt,
        )
}

data class TriviaResult(
    val correct: Boolean,
    val correctAnswer: String,
    val pointsEarned: Int,
    val totalScore: Int,
)

private fun modeFromRaw(value: String): SessionMode = when (value) {
    SessionMode.HOST.raw -> SessionMode.HOST
    else -> SessionMode.PARTY
}

private fun statusFromRaw(value: String): SessionStatus = when (value) {
    SessionStatus.LOBBY.raw -> SessionStatus.LOBBY
    SessionStatus.PAUSED.raw -> SessionStatus.PAUSED
    SessionStatus.FINISHED.raw -> SessionStatus.FINISHED
    "active" -> SessionStatus.PLAYING
    "ended" -> SessionStatus.FINISHED
    else -> SessionStatus.PLAYING
}

private fun roundStatusFromRaw(value: String): RoundStatus = when (value) {
    RoundStatus.PENDING.raw -> RoundStatus.PENDING
    RoundStatus.REVEALED.raw -> RoundStatus.REVEALED
    RoundStatus.FINISHED.raw -> RoundStatus.FINISHED
    "active" -> RoundStatus.PLAYING
    "ended" -> RoundStatus.FINISHED
    else -> RoundStatus.PLAYING
}

fun TuneTriviaSessionDto.toModel(): TuneTriviaSession = TuneTriviaSession(
    id = id,
    code = code,
    name = name,
    hostUsername = hostUsername,
    mode = modeFromRaw(mode),
    status = statusFromRaw(status),
    maxSongs = maxSongs,
    secondsPerSong = secondsPerSong,
    enableTrivia = enableTrivia,
    playerCount = playerCount,
    roundCount = roundCount,
    createdAt = createdAt,
)

fun TuneTriviaPlayerDto.toModel(): TuneTriviaPlayer = TuneTriviaPlayer(
    id = id,
    displayName = displayName,
    isHost = isHost,
    totalScore = totalScore,
    joinedAt = joinedAt,
)

fun TuneTriviaRoundDto.toModel(): TuneTriviaRound = TuneTriviaRound(
    id = id,
    roundNumber = roundNumber,
    status = roundStatusFromRaw(status),
    trackName = trackName,
    artistName = artistName,
    albumName = albumName,
    albumArtUrl = albumArtUrl,
    previewUrl = previewUrl,
    triviaQuestion = triviaQuestion,
    triviaOptions = triviaOptions,
    triviaAnswer = triviaAnswer,
    startedAt = startedAt,
    revealedAt = revealedAt,
)

fun TuneTriviaGuessDto.toModel(): TuneTriviaGuess = TuneTriviaGuess(
    id = id,
    player = player,
    playerName = playerName,
    songGuess = songGuess,
    artistGuess = artistGuess,
    triviaGuess = triviaGuess,
    songCorrect = songCorrect,
    artistCorrect = artistCorrect,
    triviaCorrect = triviaCorrect,
    pointsEarned = pointsEarned,
    submittedAt = submittedAt,
)

fun LeaderboardEntryDto.toModel(): LeaderboardEntry = LeaderboardEntry(
    id = id,
    displayName = displayName,
    totalScore = totalScore,
    totalGames = totalGames,
    totalCorrectSongs = totalCorrectSongs,
    totalCorrectArtists = totalCorrectArtists,
    totalCorrectTrivia = totalCorrectTrivia,
    lastPlayedAt = lastPlayedAt,
)

fun SpotifyTrackDto.toModel(): SpotifyTrack = SpotifyTrack(
    id = id,
    name = name,
    artistName = artistName,
    albumName = albumName,
    albumArtUrl = albumArtUrl,
    previewUrl = previewUrl,
)

fun SessionDetailResponse.toModel(): SessionDetail = SessionDetail(
    id = id,
    code = code,
    name = name,
    hostUsername = hostUsername,
    mode = modeFromRaw(mode),
    status = statusFromRaw(status),
    maxSongs = maxSongs,
    secondsPerSong = secondsPerSong,
    enableTrivia = enableTrivia,
    playerCount = playerCount,
    roundCount = roundCount,
    createdAt = createdAt,
    players = players.map { it.toModel() },
    rounds = rounds.map { it.toModel() },
)

fun TriviaSubmitResponse.toModel(): TriviaResult = TriviaResult(
    correct = correct,
    correctAnswer = correctAnswer,
    pointsEarned = pointsEarned,
    totalScore = totalScore,
)
