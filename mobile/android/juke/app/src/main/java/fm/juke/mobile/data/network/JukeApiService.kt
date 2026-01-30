package fm.juke.mobile.data.network

import fm.juke.mobile.data.network.dto.FeaturedGenreDto
import fm.juke.mobile.data.network.dto.LoginRequest
import fm.juke.mobile.data.network.dto.LoginResponse
import fm.juke.mobile.data.network.dto.MusicProfileDto
import fm.juke.mobile.data.network.dto.PaginatedAlbums
import fm.juke.mobile.data.network.dto.PaginatedArtists
import fm.juke.mobile.data.network.dto.PaginatedProfileSearch
import fm.juke.mobile.data.network.dto.PaginatedTracks
import fm.juke.mobile.data.network.dto.RegisterRequest
import fm.juke.mobile.data.network.dto.RegisterResponse
import kotlinx.serialization.json.JsonObject
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface JukeApiService {
    @POST("api/v1/auth/api-auth-token/")
    suspend fun login(@Body body: LoginRequest): LoginResponse

    @POST("api/v1/auth/accounts/register/")
    suspend fun register(@Body body: RegisterRequest): RegisterResponse

    @POST("api/v1/auth/session/logout/")
    suspend fun logout(@Header("Authorization") token: String)

    @GET("api/v1/music-profiles/me/")
    suspend fun myProfile(@Header("Authorization") token: String): MusicProfileDto

    @PATCH("api/v1/music-profiles/me/")
    suspend fun patchProfile(
        @Header("Authorization") token: String,
        @Body body: JsonObject,
    )

    @GET("api/v1/music-profiles/search/")
    suspend fun searchProfiles(
        @Header("Authorization") token: String,
        @Query("q") query: String,
    ): PaginatedProfileSearch

    @GET("api/v1/music-profiles/{username}/")
    suspend fun getProfile(
        @Header("Authorization") token: String,
        @Path("username") username: String,
    ): MusicProfileDto

    @GET("api/v1/artists/")
    suspend fun searchArtists(
        @Header("Authorization") token: String,
        @Query("q") query: String,
        @Query("external") external: Boolean = true,
    ): PaginatedArtists

    @GET("api/v1/albums/")
    suspend fun searchAlbums(
        @Header("Authorization") token: String,
        @Query("q") query: String,
        @Query("external") external: Boolean = true,
    ): PaginatedAlbums

    @GET("api/v1/tracks/")
    suspend fun searchTracks(
        @Header("Authorization") token: String,
        @Query("q") query: String,
        @Query("external") external: Boolean = true,
    ): PaginatedTracks

    @GET("api/v1/genres/featured/")
    suspend fun featuredGenres(
        @Header("Authorization") token: String,
    ): List<FeaturedGenreDto>
}
