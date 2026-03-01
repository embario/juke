package fm.tunetrivia.mobile.testutil

import fm.tunetrivia.mobile.data.network.TuneTriviaApiService
import fm.tunetrivia.mobile.data.network.dto.AddTrackRequest
import fm.tunetrivia.mobile.data.network.dto.CreateSessionRequest
import fm.tunetrivia.mobile.data.network.dto.JoinSessionRequest
import fm.tunetrivia.mobile.data.network.dto.LeaderboardEntryDto
import fm.tunetrivia.mobile.data.network.dto.SessionDetailResponse
import fm.tunetrivia.mobile.data.network.dto.SpotifyTrackDto
import fm.tunetrivia.mobile.data.network.dto.SubmitGuessRequest
import fm.tunetrivia.mobile.data.network.dto.SubmitTriviaRequest
import fm.tunetrivia.mobile.data.network.dto.TriviaSubmitResponse
import fm.tunetrivia.mobile.data.network.dto.TuneTriviaGuessDto
import fm.tunetrivia.mobile.data.network.dto.TuneTriviaPlayerDto
import fm.tunetrivia.mobile.data.network.dto.TuneTriviaRoundDto
import fm.tunetrivia.mobile.data.network.dto.TuneTriviaSessionDto
import kotlinx.coroutines.delay

object TestFixtures {
    fun sessionDto(
        id: Int = 1,
        mode: String = "party",
        status: String = "lobby",
    ) = TuneTriviaSessionDto(
        id = id,
        code = "ABC123",
        name = "Friday Night",
        hostUsername = "host",
        mode = mode,
        status = status,
        maxSongs = 10,
        secondsPerSong = 20,
        enableTrivia = true,
        playerCount = 2,
        roundCount = 3,
        createdAt = "2026-01-01T00:00:00Z",
    )

    fun playerDto(id: Int = 1, isHost: Boolean = false) = TuneTriviaPlayerDto(
        id = id,
        displayName = if (isHost) "host" else "player$id",
        isHost = isHost,
        totalScore = 100,
        joinedAt = "2026-01-01T00:00:00Z",
    )

    fun roundDto(id: Int = 1, status: String = "playing", triviaOptions: List<String>? = null) = TuneTriviaRoundDto(
        id = id,
        roundNumber = 1,
        status = status,
        trackName = "Song A",
        artistName = "Artist A",
        albumName = "Album A",
        albumArtUrl = null,
        previewUrl = "https://example.com/preview.mp3",
        triviaQuestion = if (triviaOptions != null) "Question" else null,
        triviaOptions = triviaOptions,
        triviaAnswer = "Answer",
        startedAt = null,
        revealedAt = null,
    )

    fun detailResponse(
        id: Int = 1,
        mode: String = "party",
        status: String = "lobby",
    ) = SessionDetailResponse(
        id = id,
        code = "ABC123",
        name = "Friday Night",
        hostUsername = "host",
        mode = mode,
        status = status,
        maxSongs = 10,
        secondsPerSong = 20,
        enableTrivia = true,
        playerCount = 2,
        roundCount = 1,
        createdAt = "2026-01-01T00:00:00Z",
        players = listOf(playerDto(id = 11, isHost = true), playerDto(id = 12)),
        rounds = listOf(roundDto()),
    )

    fun guessDto() = TuneTriviaGuessDto(
        id = 1,
        player = 12,
        playerName = "player12",
        songGuess = "Song A",
        artistGuess = "Artist A",
        triviaGuess = null,
        songCorrect = true,
        artistCorrect = true,
        triviaCorrect = false,
        pointsEarned = 2,
        submittedAt = "2026-01-01T00:00:00Z",
    )

    fun leaderboardDto(id: Int = 1) = LeaderboardEntryDto(
        id = id,
        displayName = "player$id",
        totalScore = 500,
        totalGames = 5,
        totalCorrectSongs = 10,
        totalCorrectArtists = 8,
        totalCorrectTrivia = 4,
        lastPlayedAt = "2026-01-01T00:00:00Z",
    )
}

class FakeTuneTriviaApiService : TuneTriviaApiService {
    var lastAuthToken: String? = null
    var lastJoinToken: String? = null
    var lastCreateRequest: CreateSessionRequest? = null
    var lastJoinRequest: JoinSessionRequest? = null
    var lastSubmitGuessRequest: SubmitGuessRequest? = null

    var createSessionResult: SessionDetailResponse = TestFixtures.detailResponse()
    var joinSessionResult: SessionDetailResponse = TestFixtures.detailResponse()
    var getSessionResult: SessionDetailResponse = TestFixtures.detailResponse()
    var mySessionsResult: List<TuneTriviaSessionDto> = listOf(TestFixtures.sessionDto())
    var leaderboardResult: List<LeaderboardEntryDto> = listOf(TestFixtures.leaderboardDto())
    var searchTracksResult: List<SpotifyTrackDto> = listOf(
        SpotifyTrackDto("t1", "Song A", "Artist A", "Album A", null, null),
    )

    var mySessionsError: Throwable? = null
    var leaderboardError: Throwable? = null
    var joinError: Throwable? = null
    var createError: Throwable? = null
    var submitGuessError: Throwable? = null
    var addTrackError: Throwable? = null
    var autoSelectError: Throwable? = null
    var awardPointsError: Throwable? = null
    var addTrackDelayMs: Long = 0

    override suspend fun createSession(token: String, body: CreateSessionRequest): SessionDetailResponse {
        lastAuthToken = token
        lastCreateRequest = body
        createError?.let { throw it }
        return createSessionResult
    }

    override suspend fun joinSession(token: String?, body: JoinSessionRequest): SessionDetailResponse {
        lastJoinToken = token
        lastJoinRequest = body
        joinError?.let { throw it }
        return joinSessionResult
    }

    override suspend fun getSession(token: String?, sessionId: Int): SessionDetailResponse = getSessionResult

    override suspend fun getMySessions(token: String): List<TuneTriviaSessionDto> {
        lastAuthToken = token
        mySessionsError?.let { throw it }
        return mySessionsResult
    }

    override suspend fun startSession(token: String, sessionId: Int): SessionDetailResponse = getSessionResult

    override suspend fun pauseSession(token: String, sessionId: Int): TuneTriviaSessionDto = TestFixtures.sessionDto()

    override suspend fun resumeSession(token: String, sessionId: Int): TuneTriviaSessionDto = TestFixtures.sessionDto(status = "playing")

    override suspend fun endSession(token: String, sessionId: Int): TuneTriviaSessionDto = TestFixtures.sessionDto(status = "finished")

    override suspend fun nextRound(token: String, sessionId: Int): TuneTriviaRoundDto = TestFixtures.roundDto(status = "playing")

    override suspend fun revealRound(token: String, sessionId: Int): TuneTriviaRoundDto = TestFixtures.roundDto(status = "revealed")

    override suspend fun addTrack(token: String, sessionId: Int, body: AddTrackRequest): TuneTriviaRoundDto {
        if (addTrackDelayMs > 0) delay(addTrackDelayMs)
        addTrackError?.let { throw it }
        return TestFixtures.roundDto()
    }

    override suspend fun autoSelectTracks(token: String, sessionId: Int, count: Int): List<TuneTriviaRoundDto> {
        autoSelectError?.let { throw it }
        return List(count.coerceAtLeast(0)) { TestFixtures.roundDto(id = it + 1) }
    }

    override suspend fun searchTracks(token: String, query: String): List<SpotifyTrackDto> = searchTracksResult

    override suspend fun submitGuess(token: String?, roundId: Int, body: SubmitGuessRequest): TuneTriviaGuessDto {
        lastSubmitGuessRequest = body
        submitGuessError?.let { throw it }
        return TestFixtures.guessDto()
    }

    override suspend fun getRoundGuesses(token: String?, roundId: Int): List<TuneTriviaGuessDto> = listOf(TestFixtures.guessDto())

    override suspend fun submitTrivia(token: String?, roundId: Int, body: SubmitTriviaRequest): TriviaSubmitResponse =
        TriviaSubmitResponse(correct = true, correctAnswer = "A", pointsEarned = 1, totalScore = 10)

    override suspend fun addManualPlayer(token: String, sessionId: Int, body: Map<String, String>): TuneTriviaPlayerDto =
        TestFixtures.playerDto(id = 22)

    override suspend fun awardPoints(token: String, playerId: Int, body: Map<String, Int>): TuneTriviaPlayerDto {
        awardPointsError?.let { throw it }
        return TestFixtures.playerDto(id = playerId)
    }

    override suspend fun leaderboard(limit: Int): List<LeaderboardEntryDto> {
        leaderboardError?.let { throw it }
        return leaderboardResult
    }
}
