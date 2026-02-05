package fm.tunetrivia.mobile.data.network.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class TuneTriviaSessionDto(
    val id: Int,
    val code: String,
    val name: String,
    @SerialName("host_username") val hostUsername: String,
    val mode: String,
    val status: String,
    @SerialName("max_songs") val maxSongs: Int,
    @SerialName("seconds_per_song") val secondsPerSong: Int,
    @SerialName("enable_trivia") val enableTrivia: Boolean,
    @SerialName("player_count") val playerCount: Int? = null,
    @SerialName("round_count") val roundCount: Int? = null,
    @SerialName("created_at") val createdAt: String,
)

@Serializable
data class TuneTriviaPlayerDto(
    val id: Int,
    @SerialName("display_name") val displayName: String,
    @SerialName("is_host") val isHost: Boolean,
    @SerialName("total_score") val totalScore: Int,
    @SerialName("joined_at") val joinedAt: String,
)

@Serializable
data class TuneTriviaRoundDto(
    val id: Int,
    @SerialName("round_number") val roundNumber: Int,
    val status: String,
    @SerialName("track_name") val trackName: String,
    @SerialName("artist_name") val artistName: String,
    @SerialName("album_name") val albumName: String? = null,
    @SerialName("album_art_url") val albumArtUrl: String? = null,
    @SerialName("preview_url") val previewUrl: String? = null,
    @SerialName("trivia_question") val triviaQuestion: String? = null,
    @SerialName("trivia_options") val triviaOptions: List<String>? = null,
    @SerialName("trivia_answer") val triviaAnswer: String? = null,
    @SerialName("started_at") val startedAt: String? = null,
    @SerialName("revealed_at") val revealedAt: String? = null,
)

@Serializable
data class TuneTriviaGuessDto(
    val id: Int,
    val player: Int,
    @SerialName("player_name") val playerName: String,
    @SerialName("song_guess") val songGuess: String? = null,
    @SerialName("artist_guess") val artistGuess: String? = null,
    @SerialName("trivia_guess") val triviaGuess: String? = null,
    @SerialName("song_correct") val songCorrect: Boolean,
    @SerialName("artist_correct") val artistCorrect: Boolean,
    @SerialName("trivia_correct") val triviaCorrect: Boolean,
    @SerialName("points_earned") val pointsEarned: Int,
    @SerialName("submitted_at") val submittedAt: String,
)

@Serializable
data class LeaderboardEntryDto(
    val id: Int,
    @SerialName("display_name") val displayName: String,
    @SerialName("total_score") val totalScore: Int,
    @SerialName("total_games") val totalGames: Int,
    @SerialName("total_correct_songs") val totalCorrectSongs: Int,
    @SerialName("total_correct_artists") val totalCorrectArtists: Int,
    @SerialName("total_correct_trivia") val totalCorrectTrivia: Int,
    @SerialName("last_played_at") val lastPlayedAt: String,
)

@Serializable
data class CreateSessionRequest(
    val name: String,
    val mode: String,
    @SerialName("max_songs") val maxSongs: Int,
    @SerialName("seconds_per_song") val secondsPerSong: Int,
    @SerialName("enable_trivia") val enableTrivia: Boolean,
    @SerialName("auto_select_decade") val autoSelectDecade: String? = null,
    @SerialName("auto_select_genre") val autoSelectGenre: String? = null,
    @SerialName("auto_select_artist") val autoSelectArtist: String? = null,
)

@Serializable
data class JoinSessionRequest(
    val code: String,
    @SerialName("display_name") val displayName: String? = null,
)

@Serializable
data class AddTrackRequest(
    @SerialName("track_id") val trackId: String,
)

@Serializable
data class SubmitGuessRequest(
    @SerialName("song_guess") val songGuess: String? = null,
    @SerialName("artist_guess") val artistGuess: String? = null,
)

@Serializable
data class SubmitTriviaRequest(
    @SerialName("trivia_guess") val triviaGuess: String,
)

@Serializable
data class TriviaSubmitResponse(
    val correct: Boolean,
    @SerialName("correct_answer") val correctAnswer: String,
    @SerialName("points_earned") val pointsEarned: Int,
    @SerialName("total_score") val totalScore: Int,
)

@Serializable
data class SessionDetailResponse(
    val id: Int,
    val code: String,
    val name: String,
    @SerialName("host_username") val hostUsername: String,
    val mode: String,
    val status: String,
    @SerialName("max_songs") val maxSongs: Int,
    @SerialName("seconds_per_song") val secondsPerSong: Int,
    @SerialName("enable_trivia") val enableTrivia: Boolean,
    @SerialName("player_count") val playerCount: Int? = null,
    @SerialName("round_count") val roundCount: Int? = null,
    @SerialName("created_at") val createdAt: String,
    val players: List<TuneTriviaPlayerDto> = emptyList(),
    val rounds: List<TuneTriviaRoundDto> = emptyList(),
)

@Serializable
data class SpotifyTrackDto(
    val id: String,
    val name: String,
    @SerialName("artist_name") val artistName: String,
    @SerialName("album_name") val albumName: String,
    @SerialName("album_art_url") val albumArtUrl: String? = null,
    @SerialName("preview_url") val previewUrl: String? = null,
)

