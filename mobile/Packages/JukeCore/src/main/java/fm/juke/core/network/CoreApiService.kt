package fm.juke.core.network

import fm.juke.core.auth.dto.LoginRequest
import fm.juke.core.auth.dto.LoginResponse
import fm.juke.core.auth.dto.RegisterRequest
import fm.juke.core.auth.dto.RegisterResponse
import fm.juke.core.catalog.dto.FeaturedGenreDto
import fm.juke.core.catalog.dto.PaginatedAlbums
import fm.juke.core.catalog.dto.PaginatedArtists
import fm.juke.core.catalog.dto.PaginatedTracks
import fm.juke.core.profile.dto.MusicProfileDto
import fm.juke.core.profile.dto.PaginatedProfileSearch
import kotlinx.serialization.json.JsonObject
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface CoreApiService {
    // Auth
    @POST("api/v1/auth/api-auth-token/")
    suspend fun login(@Body body: LoginRequest): LoginResponse

    @POST("api/v1/auth/accounts/register/")
    suspend fun register(@Body body: RegisterRequest): RegisterResponse

    @POST("api/v1/auth/session/logout/")
    suspend fun logout(@Header("Authorization") token: String)

    // Profile
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

    // Catalog
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
