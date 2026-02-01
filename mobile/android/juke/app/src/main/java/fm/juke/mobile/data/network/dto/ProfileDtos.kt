package fm.juke.mobile.data.network.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class MusicProfileDto(
    val id: Int? = null,
    val username: String? = null,
    val name: String? = null,
    @SerialName("display_name") val displayName: String? = null,
    val tagline: String? = null,
    val bio: String? = null,
    val location: String? = null,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    @SerialName("favorite_genres") val favoriteGenres: List<String> = emptyList(),
    @SerialName("favorite_artists") val favoriteArtists: List<String> = emptyList(),
    @SerialName("favorite_albums") val favoriteAlbums: List<String> = emptyList(),
    @SerialName("favorite_tracks") val favoriteTracks: List<String> = emptyList(),
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("modified_at") val modifiedAt: String? = null,
    @SerialName("is_owner") val isOwner: Boolean? = null,
)

@Serializable
data class ProfileSearchResponse(
    val results: List<ProfileSearchEntry> = emptyList(),
)

@Serializable
data class ProfileSearchEntry(
    val username: String,
    @SerialName("display_name") val displayName: String? = null,
    val tagline: String? = null,
    @SerialName("avatar_url") val avatarUrl: String? = null,
)
