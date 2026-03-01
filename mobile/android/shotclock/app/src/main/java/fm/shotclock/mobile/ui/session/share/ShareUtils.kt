package fm.shotclock.mobile.ui.session.share

import android.content.Context
import fm.juke.core.share.shareSmsOrText
import fm.shotclock.mobile.model.SessionTrack

fun shareInvite(context: Context, inviteCode: String, title: String) {
    val message = "Join my ShotClock session \"$title\"! Use invite code: $inviteCode"
    shareSmsOrText(
        context = context,
        message = message,
        chooserTitle = "Share invite",
    )
}

fun sharePlaylist(context: Context, tracks: List<SessionTrack>, title: String) {
    val trackList = tracks.mapIndexed { index, track ->
        "${index + 1}. ${track.trackName} - ${track.trackArtist}"
    }.joinToString("\n")
    val message = "ShotClock Playlist: $title\n\n$trackList"
    shareSmsOrText(
        context = context,
        message = message,
        chooserTitle = "Share playlist",
    )
}
