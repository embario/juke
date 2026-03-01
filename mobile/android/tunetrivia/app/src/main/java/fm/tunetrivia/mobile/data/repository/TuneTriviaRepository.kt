package fm.tunetrivia.mobile.data.repository

import fm.tunetrivia.mobile.data.network.TuneTriviaApiService
import fm.tunetrivia.mobile.data.network.dto.AddTrackRequest
import fm.tunetrivia.mobile.data.network.dto.CreateSessionRequest
import fm.tunetrivia.mobile.data.network.dto.JoinSessionRequest
import fm.tunetrivia.mobile.data.network.dto.SubmitGuessRequest
import fm.tunetrivia.mobile.data.network.dto.SubmitTriviaRequest
import fm.juke.core.auth.AuthRepositoryContract
import fm.tunetrivia.mobile.model.LeaderboardEntry
import fm.tunetrivia.mobile.model.SessionDetail
import fm.tunetrivia.mobile.model.SpotifyTrack
import fm.tunetrivia.mobile.model.TriviaResult
import fm.tunetrivia.mobile.model.TuneTriviaGuess
import fm.tunetrivia.mobile.model.TuneTriviaPlayer
import fm.tunetrivia.mobile.model.TuneTriviaRound
import fm.tunetrivia.mobile.model.TuneTriviaSession
import fm.tunetrivia.mobile.model.toModel

class TuneTriviaRepository(
    private val api: TuneTriviaApiService,
    private val authRepository: AuthRepositoryContract,
) {
    suspend fun createSession(
        name: String,
        mode: String,
        maxSongs: Int,
        secondsPerSong: Int,
        enableTrivia: Boolean,
        autoSelectDecade: String? = null,
        autoSelectGenre: String? = null,
        autoSelectArtist: String? = null,
    ): Result<SessionDetail> = runCatching {
        val token = requireToken()
        api.createSession(
            token = token,
            body = CreateSessionRequest(
                name = name,
                mode = mode,
                maxSongs = maxSongs,
                secondsPerSong = secondsPerSong,
                enableTrivia = enableTrivia,
                autoSelectDecade = autoSelectDecade,
                autoSelectGenre = autoSelectGenre,
                autoSelectArtist = autoSelectArtist,
            ),
        ).toModel()
    }

    suspend fun joinSession(code: String, displayName: String?): Result<SessionDetail> = runCatching {
        val token = authRepository.currentSession()?.let { "Token ${it.token}" }
        api.joinSession(
            token = token,
            body = JoinSessionRequest(code = code, displayName = displayName),
        ).toModel()
    }

    suspend fun getSession(sessionId: Int): Result<SessionDetail> = runCatching {
        val token = authRepository.currentSession()?.let { "Token ${it.token}" }
        api.getSession(token = token, sessionId = sessionId).toModel()
    }

    suspend fun getMySessions(): Result<List<TuneTriviaSession>> = runCatching {
        val token = requireToken()
        api.getMySessions(token).map { it.toModel() }
    }

    suspend fun startGame(sessionId: Int): Result<SessionDetail> = runCatching {
        val token = requireToken()
        api.startSession(token, sessionId).toModel()
    }

    suspend fun pauseGame(sessionId: Int): Result<TuneTriviaSession> = runCatching {
        val token = requireToken()
        api.pauseSession(token, sessionId).toModel()
    }

    suspend fun resumeGame(sessionId: Int): Result<TuneTriviaSession> = runCatching {
        val token = requireToken()
        api.resumeSession(token, sessionId).toModel()
    }

    suspend fun endGame(sessionId: Int): Result<TuneTriviaSession> = runCatching {
        val token = requireToken()
        api.endSession(token, sessionId).toModel()
    }

    suspend fun nextRound(sessionId: Int): Result<TuneTriviaRound> = runCatching {
        val token = requireToken()
        api.nextRound(token, sessionId).toModel()
    }

    suspend fun revealRound(sessionId: Int): Result<TuneTriviaRound> = runCatching {
        val token = requireToken()
        api.revealRound(token, sessionId).toModel()
    }

    suspend fun addTrack(sessionId: Int, trackId: String): Result<TuneTriviaRound> = runCatching {
        val token = requireToken()
        api.addTrack(token, sessionId, AddTrackRequest(trackId)).toModel()
    }

    suspend fun autoSelectTracks(sessionId: Int, count: Int): Result<List<TuneTriviaRound>> = runCatching {
        val token = requireToken()
        api.autoSelectTracks(token, sessionId, count).map { it.toModel() }
    }

    suspend fun searchTracks(query: String): Result<List<SpotifyTrack>> = runCatching {
        val token = requireToken()
        api.searchTracks(token, query).map { it.toModel() }
    }

    suspend fun submitGuess(
        roundId: Int,
        songGuess: String?,
        artistGuess: String?,
    ): Result<TuneTriviaGuess> = runCatching {
        val token = authRepository.currentSession()?.let { "Token ${it.token}" }
        api.submitGuess(token, roundId, SubmitGuessRequest(songGuess, artistGuess)).toModel()
    }

    suspend fun submitTrivia(roundId: Int, answer: String): Result<TriviaResult> = runCatching {
        val token = authRepository.currentSession()?.let { "Token ${it.token}" }
        api.submitTrivia(token, roundId, SubmitTriviaRequest(answer)).toModel()
    }

    suspend fun addManualPlayer(sessionId: Int, displayName: String): Result<TuneTriviaPlayer> = runCatching {
        val token = requireToken()
        api.addManualPlayer(token, sessionId, mapOf("display_name" to displayName)).toModel()
    }

    suspend fun awardPoints(playerId: Int, points: Int): Result<TuneTriviaPlayer> = runCatching {
        val token = requireToken()
        api.awardPoints(token, playerId, mapOf("points" to points)).toModel()
    }

    suspend fun leaderboard(limit: Int = 50): Result<List<LeaderboardEntry>> = runCatching {
        api.leaderboard(limit).map { it.toModel() }
    }

    private suspend fun requireToken(): String {
        val session = authRepository.currentSession()
        checkNotNull(session) { "No active session token" }
        return "Token ${session.token}"
    }
}
