package fm.shotclock.mobile.data.network

import fm.juke.core.network.CoreApiService
import fm.shotclock.mobile.data.network.dto.AddTrackRequest
import fm.shotclock.mobile.data.network.dto.CreateSessionRequest
import fm.shotclock.mobile.data.network.dto.ImportSessionTracksRequest
import fm.shotclock.mobile.data.network.dto.ImportSessionTracksResponse
import fm.shotclock.mobile.data.network.dto.JoinSessionRequest
import fm.shotclock.mobile.data.network.dto.SessionDto
import fm.shotclock.mobile.data.network.dto.SessionPlayerDto
import fm.shotclock.mobile.data.network.dto.SessionStateDto
import fm.shotclock.mobile.data.network.dto.SessionTrackDto
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path

interface ShotClockApiService : CoreApiService {
    @POST("api/v1/powerhour/sessions/")
    suspend fun createSession(
        @Header("Authorization") token: String,
        @Body body: CreateSessionRequest,
    ): SessionDto

    @GET("api/v1/powerhour/sessions/")
    suspend fun listSessions(
        @Header("Authorization") token: String,
    ): List<SessionDto>

    @POST("api/v1/powerhour/sessions/join/")
    suspend fun joinSession(
        @Header("Authorization") token: String,
        @Body body: JoinSessionRequest,
    ): SessionDto

    @GET("api/v1/powerhour/sessions/{id}/")
    suspend fun getSession(
        @Header("Authorization") token: String,
        @Path("id") sessionId: String,
    ): SessionDto

    @DELETE("api/v1/powerhour/sessions/{id}/")
    suspend fun deleteSession(
        @Header("Authorization") token: String,
        @Path("id") sessionId: String,
    )

    @GET("api/v1/powerhour/sessions/{id}/players/")
    suspend fun listPlayers(
        @Header("Authorization") token: String,
        @Path("id") sessionId: String,
    ): List<SessionPlayerDto>

    @GET("api/v1/powerhour/sessions/{id}/tracks/")
    suspend fun listTracks(
        @Header("Authorization") token: String,
        @Path("id") sessionId: String,
    ): List<SessionTrackDto>

    @POST("api/v1/powerhour/sessions/{id}/start/")
    suspend fun startSession(
        @Header("Authorization") token: String,
        @Path("id") sessionId: String,
    ): SessionStateDto

    @POST("api/v1/powerhour/sessions/{id}/pause/")
    suspend fun pauseSession(
        @Header("Authorization") token: String,
        @Path("id") sessionId: String,
    ): SessionStateDto

    @POST("api/v1/powerhour/sessions/{id}/resume/")
    suspend fun resumeSession(
        @Header("Authorization") token: String,
        @Path("id") sessionId: String,
    ): SessionStateDto

    @POST("api/v1/powerhour/sessions/{id}/end/")
    suspend fun endSession(
        @Header("Authorization") token: String,
        @Path("id") sessionId: String,
    ): SessionStateDto

    @POST("api/v1/powerhour/sessions/{id}/next/")
    suspend fun nextTrack(
        @Header("Authorization") token: String,
        @Path("id") sessionId: String,
    ): SessionStateDto

    @POST("api/v1/powerhour/sessions/{id}/tracks/")
    suspend fun addTrack(
        @Header("Authorization") token: String,
        @Path("id") sessionId: String,
        @Body body: AddTrackRequest,
    ): SessionTrackDto

    @DELETE("api/v1/powerhour/sessions/{id}/tracks/{trackId}/")
    suspend fun removeTrack(
        @Header("Authorization") token: String,
        @Path("id") sessionId: String,
        @Path("trackId") trackId: String,
    )

    @POST("api/v1/powerhour/sessions/{id}/tracks/import-session/")
    suspend fun importSessionTracks(
        @Header("Authorization") token: String,
        @Path("id") sessionId: String,
        @Body body: ImportSessionTracksRequest,
    ): ImportSessionTracksResponse
}
