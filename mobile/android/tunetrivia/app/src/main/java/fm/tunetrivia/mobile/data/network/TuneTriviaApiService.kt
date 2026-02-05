package fm.tunetrivia.mobile.data.network

import fm.tunetrivia.mobile.data.network.dto.AddTrackRequest
import fm.tunetrivia.mobile.data.network.dto.CreateSessionRequest
import fm.tunetrivia.mobile.data.network.dto.JoinSessionRequest
import fm.tunetrivia.mobile.data.network.dto.LeaderboardEntryDto
import fm.tunetrivia.mobile.data.network.dto.LoginRequest
import fm.tunetrivia.mobile.data.network.dto.LoginResponse
import fm.tunetrivia.mobile.data.network.dto.RegisterRequest
import fm.tunetrivia.mobile.data.network.dto.RegisterResponse
import fm.tunetrivia.mobile.data.network.dto.SessionDetailResponse
import fm.tunetrivia.mobile.data.network.dto.SpotifyTrackDto
import fm.tunetrivia.mobile.data.network.dto.SubmitGuessRequest
import fm.tunetrivia.mobile.data.network.dto.SubmitTriviaRequest
import fm.tunetrivia.mobile.data.network.dto.TriviaSubmitResponse
import fm.tunetrivia.mobile.data.network.dto.TuneTriviaGuessDto
import fm.tunetrivia.mobile.data.network.dto.TuneTriviaPlayerDto
import fm.tunetrivia.mobile.data.network.dto.TuneTriviaRoundDto
import fm.tunetrivia.mobile.data.network.dto.TuneTriviaSessionDto
import retrofit2.http.Body
import retrofit2.http.Header
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface TuneTriviaApiService {
    @POST("api/v1/auth/api-auth-token/")
    suspend fun login(@Body body: LoginRequest): LoginResponse

    @POST("api/v1/auth/accounts/register/")
    suspend fun register(@Body body: RegisterRequest): RegisterResponse

    @POST("api/v1/auth/session/logout/")
    suspend fun logout(@Header("Authorization") token: String)

    @POST("api/v1/tunetrivia/sessions/")
    suspend fun createSession(
        @Header("Authorization") token: String,
        @Body body: CreateSessionRequest,
    ): SessionDetailResponse

    @POST("api/v1/tunetrivia/sessions/join/")
    suspend fun joinSession(
        @Header("Authorization") token: String?,
        @Body body: JoinSessionRequest,
    ): SessionDetailResponse

    @GET("api/v1/tunetrivia/sessions/{id}/")
    suspend fun getSession(
        @Header("Authorization") token: String?,
        @Path("id") sessionId: Int,
    ): SessionDetailResponse

    @GET("api/v1/tunetrivia/sessions/mine/")
    suspend fun getMySessions(
        @Header("Authorization") token: String,
    ): List<TuneTriviaSessionDto>

    @POST("api/v1/tunetrivia/sessions/{id}/start/")
    suspend fun startSession(
        @Header("Authorization") token: String,
        @Path("id") sessionId: Int,
    ): SessionDetailResponse

    @POST("api/v1/tunetrivia/sessions/{id}/pause/")
    suspend fun pauseSession(
        @Header("Authorization") token: String,
        @Path("id") sessionId: Int,
    ): TuneTriviaSessionDto

    @POST("api/v1/tunetrivia/sessions/{id}/resume/")
    suspend fun resumeSession(
        @Header("Authorization") token: String,
        @Path("id") sessionId: Int,
    ): TuneTriviaSessionDto

    @POST("api/v1/tunetrivia/sessions/{id}/end/")
    suspend fun endSession(
        @Header("Authorization") token: String,
        @Path("id") sessionId: Int,
    ): TuneTriviaSessionDto

    @POST("api/v1/tunetrivia/sessions/{id}/next-round/")
    suspend fun nextRound(
        @Header("Authorization") token: String,
        @Path("id") sessionId: Int,
    ): TuneTriviaRoundDto

    @POST("api/v1/tunetrivia/sessions/{id}/reveal/")
    suspend fun revealRound(
        @Header("Authorization") token: String,
        @Path("id") sessionId: Int,
    ): TuneTriviaRoundDto

    @POST("api/v1/tunetrivia/sessions/{id}/tracks/")
    suspend fun addTrack(
        @Header("Authorization") token: String,
        @Path("id") sessionId: Int,
        @Body body: AddTrackRequest,
    ): TuneTriviaRoundDto

    @POST("api/v1/tunetrivia/sessions/{id}/auto-select/")
    suspend fun autoSelectTracks(
        @Header("Authorization") token: String,
        @Path("id") sessionId: Int,
        @Query("count") count: Int,
    ): List<TuneTriviaRoundDto>

    @GET("api/v1/tunetrivia/sessions/search-tracks/")
    suspend fun searchTracks(
        @Header("Authorization") token: String,
        @Query("q") query: String,
    ): List<SpotifyTrackDto>

    @POST("api/v1/tunetrivia/rounds/{id}/guess/")
    suspend fun submitGuess(
        @Header("Authorization") token: String?,
        @Path("id") roundId: Int,
        @Body body: SubmitGuessRequest,
    ): TuneTriviaGuessDto

    @GET("api/v1/tunetrivia/rounds/{id}/guesses/")
    suspend fun getRoundGuesses(
        @Header("Authorization") token: String?,
        @Path("id") roundId: Int,
    ): List<TuneTriviaGuessDto>

    @POST("api/v1/tunetrivia/rounds/{id}/trivia/")
    suspend fun submitTrivia(
        @Header("Authorization") token: String?,
        @Path("id") roundId: Int,
        @Body body: SubmitTriviaRequest,
    ): TriviaSubmitResponse

    @POST("api/v1/tunetrivia/sessions/{id}/players/")
    suspend fun addManualPlayer(
        @Header("Authorization") token: String,
        @Path("id") sessionId: Int,
        @Body body: Map<String, String>,
    ): TuneTriviaPlayerDto

    @POST("api/v1/tunetrivia/players/{id}/award/")
    suspend fun awardPoints(
        @Header("Authorization") token: String,
        @Path("id") playerId: Int,
        @Body body: Map<String, Int>,
    ): TuneTriviaPlayerDto

    @GET("api/v1/tunetrivia/leaderboard/")
    suspend fun leaderboard(
        @Query("limit") limit: Int = 50,
    ): List<LeaderboardEntryDto>
}
