import SwiftUI

/// Radio section. S2 placeholder: the existing now-playing controls on the
/// 640pt record card. S3 replaces the body with the sleeve, vinyl, reaction
/// strip and FM dial (see the design reference), driven by `model.api`.
struct RadioScreen: View {
    @Environment(AppModel.self) private var model
    @Environment(\.jukeTheme) private var theme

    var body: some View {
        JukeCard {
            VStack(alignment: .leading, spacing: 18) {
                HStack(alignment: .center, spacing: 20) {
                    sleeve
                    VStack(alignment: .leading, spacing: 6) {
                        Text(model.detection.track?.title ?? "Nothing on the air yet")
                            .font(JukeFont.display(28, weight: .bold))
                            .tracking(-0.6)
                            .lineLimit(2)
                        Text(model.detection.track.map { "\($0.artist)\($0.album.map { " · \($0)" } ?? "")" }
                             ?? "Play something in Spotify or Apple Music and it shows up here.")
                            .font(JukeFont.body(15))
                            .foregroundStyle(theme.sub.color)
                            .lineLimit(2)
                    }
                    Spacer(minLength: 0)
                }
                NowPlayingBar()
            }
        }
        .frame(width: JukeMetrics.radioCardWidth)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("radio.screen")
    }

    private var sleeve: some View {
        ZStack {
            RoundedRectangle(cornerRadius: JukeRadius.sleeve, style: .continuous)
                .fill(theme.base.color)
            if let url = model.detection.track?.artworkURL {
                AsyncImage(url: url) { image in image.resizable().scaledToFill() } placeholder: { Color.clear }
            } else {
                Image(systemName: "dot.radiowaves.left.and.right")
                    .font(.system(size: 34, weight: .medium))
                    .foregroundStyle(theme.onAccent.color.opacity(0.85))
            }
        }
        .frame(width: 132, height: 132)
        .clipShape(RoundedRectangle(cornerRadius: JukeRadius.sleeve, style: .continuous))
        .shadow(color: theme.liftShadow.color, radius: theme.liftShadow.radius, y: theme.liftShadow.y)
        .accessibilityHidden(true)
    }
}
