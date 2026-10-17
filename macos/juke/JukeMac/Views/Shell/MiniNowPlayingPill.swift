import SwiftUI

/// The floating now-playing pill shown at the bottom of every section except
/// Radio: a small record in the artwork colour, the track, a note, play/pause
/// and "Open Radio".
///
/// S3 can replace `note` with the tuned station ("Next: Night Drive", "Put away").
struct MiniNowPlayingPill: View {
    @Environment(AppModel.self) private var model
    @Environment(\.jukeTheme) private var theme

    var body: some View {
        HStack(spacing: 12) {
            VinylDisc(label: theme.base.color, size: 40, isSpinning: model.detection.isPlaying)
            if let track = model.detection.track {
                Text("\(Text(track.title).bold()) · \(track.artist)")
                    .font(JukeFont.body(14))
                    .foregroundStyle(theme.ink.color)
                    .lineLimit(1)
                    .frame(maxWidth: 320, alignment: .leading)
                if let note {
                    Text(note)
                        .font(JukeFont.body(13))
                        .foregroundStyle(theme.sub.color)
                        .lineLimit(1)
                }
            } else {
                Text("Nothing playing")
                    .font(JukeFont.body(14))
                    .foregroundStyle(theme.sub.color)
            }
            if model.detection.track != nil, model.detection.canControlPlayback {
                Button {
                    Task {
                        if model.radio.isOnAir { await model.radio.togglePlayPause() } else { await model.detection.togglePlayback() }
                    }
                } label: {
                    Image(systemName: model.detection.isPlaying ? "pause.fill" : "play.fill")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(theme.onAccent.color)
                        .frame(width: JukeMetrics.minimumHitTarget, height: JukeMetrics.minimumHitTarget)
                        .background(theme.accent.color, in: Circle())
                        .contentShape(Circle())
                }
                .buttonStyle(.plain)
                .disabled(model.detection.isPlaybackBusy)
                .accessibilityLabel(model.detection.isPlaying ? "Pause" : "Play")
                .accessibilityIdentifier("miniPlayer.playPause")
            }
            Button("Open Radio") { model.section = .radio }
                .buttonStyle(JukeWellButtonStyle())
                .accessibilityIdentifier("miniPlayer.openRadio")
        }
        .padding(.vertical, 6)
        .padding(.leading, 8)
        .padding(.trailing, 6)
        .background(theme.card.color, in: Capsule())
        .shadow(color: theme.shadow.color, radius: theme.shadow.radius, y: theme.shadow.y)
        .fixedSize()
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Now playing")
        .accessibilityIdentifier("miniPlayer")
    }

    private var note: String? {
        let radio = model.radio
        if radio.isPutAway { return "Put away" }
        if radio.isOnAir, let station = radio.currentStation {
            return radio.pendingStation.map { "Next: \($0.name)" } ?? station.name
        }
        return model.detection.providerName ?? model.detection.playbackDeviceName
    }
}
