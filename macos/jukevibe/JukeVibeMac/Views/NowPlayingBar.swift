import SwiftUI

struct NowPlayingBar: View {
    @Environment(AppModel.self) private var model
    @State private var scrubPosition: TimeInterval = 0
    @State private var isScrubbing = false

    var body: some View {
        VStack(spacing: 9) {
            HStack(spacing: 13) {
                artwork
                VStack(alignment: .leading, spacing: 2) {
                    Text(model.detection.track?.title ?? "Listening for music")
                        .font(.headline)
                        .lineLimit(1)
                    Text(metadataLine)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Spacer(minLength: 12)
                playbackControls
                Circle()
                    .fill(model.detection.isAudioPresent ? model.atmosphere.primary : .secondary.opacity(0.35))
                    .frame(width: 8, height: 8)
                detectionMenu
            }

            if model.detection.playbackDuration > 0 {
                TimelineView(.periodic(from: .now, by: 0.5)) { timeline in
                    progressRow(at: timeline.date)
                }
            }

            if let error = model.detection.errorMessage {
                Text(error)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .trailing)
                    .accessibilityIdentifier("nowPlaying.error")
            }
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 11)
        .background(.ultraThinMaterial)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("nowPlaying.bar")
    }

    private var metadataLine: String {
        guard let track = model.detection.track else {
            return "Spotify and Apple Music metadata are checked automatically"
        }
        let provider = model.detection.providerName ?? "Juke Vibe"
        let album = track.album.map { " · \($0)" } ?? ""
        let device = model.detection.playbackDeviceName.map { " · \($0)" } ?? ""
        return "\(track.artist)\(album) · \(provider)\(device)"
    }

    private var playbackControls: some View {
        HStack(spacing: 5) {
            controlButton("Previous track", symbol: "backward.end.fill") {
                await model.detection.previousTrack()
            }
            controlButton(
                model.detection.isPlaying ? "Pause" : "Play",
                symbol: model.detection.isPlaying ? "pause.fill" : "play.fill"
            ) {
                await model.detection.togglePlayback()
            }
            controlButton("Next track", symbol: "forward.end.fill") {
                await model.detection.nextTrack()
            }
        }
    }

    private func controlButton(
        _ label: String,
        symbol: String,
        action: @escaping @MainActor () async -> Void
    ) -> some View {
        Button { Task { await action() } } label: {
            Image(systemName: symbol).frame(width: 24, height: 24)
        }
        .buttonStyle(.plain)
        .disabled(!model.detection.canControlPlayback || model.detection.isPlaybackBusy)
        .accessibilityLabel(label)
    }

    private var detectionMenu: some View {
        Menu {
            Picker("Music detection", selection: Bindable(model.detection).mode) {
                ForEach(MusicDetectionController.Mode.allCases) { mode in Text(mode.title).tag(mode) }
            }
            Divider()
            Button("Apply detection mode") {
                Task { await model.detection.start(token: model.session?.accessToken) }
            }
        } label: {
            Image(systemName: "ellipsis").frame(width: 28, height: 28)
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
    }

    private func progressRow(at date: Date) -> some View {
        let livePosition = model.detection.estimatedPlaybackPosition(at: date)
        let displayedPosition = isScrubbing ? scrubPosition : livePosition
        return HStack(spacing: 10) {
            Text(format(displayedPosition)).monospacedDigit()
            Slider(
                value: Binding(
                    get: { isScrubbing ? scrubPosition : livePosition },
                    set: { scrubPosition = $0 }
                ),
                in: 0...max(1, model.detection.playbackDuration),
                onEditingChanged: { editing in
                    if editing {
                        scrubPosition = livePosition
                        isScrubbing = true
                    } else {
                        let destination = scrubPosition
                        isScrubbing = false
                        Task { await model.detection.seek(to: destination) }
                    }
                }
            )
            .tint(model.atmosphere.primary)
            .controlSize(.large)
            .disabled(!model.detection.canControlPlayback || model.detection.isPlaybackBusy)
            .accessibilityLabel("Playback position")
            Text(format(model.detection.playbackDuration)).monospacedDigit()
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
    }

    @ViewBuilder private var artwork: some View {
        if let url = model.detection.track?.artworkURL {
            AsyncImage(url: url) { image in image.resizable().scaledToFill() } placeholder: { Color.white.opacity(0.08) }
                .frame(width: 48, height: 48)
                .clipShape(RoundedRectangle(cornerRadius: 8))
        } else {
            RoundedRectangle(cornerRadius: 8)
                .fill(model.atmosphere.primary.opacity(0.24))
                .frame(width: 48, height: 48)
                .overlay(Image(systemName: "waveform").foregroundStyle(model.atmosphere.primary))
        }
    }

    private func format(_ seconds: TimeInterval) -> String {
        guard seconds.isFinite else { return "0:00" }
        let total = max(0, Int(seconds))
        return "\(total / 60):\(String(format: "%02d", total % 60))"
    }
}
