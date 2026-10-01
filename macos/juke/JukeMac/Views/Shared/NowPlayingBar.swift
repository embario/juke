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
                .layoutPriority(1)
                Spacer(minLength: 12)
                playbackAccessBadge
                Circle()
                    .fill(model.detection.isAudioPresent ? model.atmosphere.primary : .secondary.opacity(0.35))
                    .frame(width: 8, height: 8)
                detectionMenu
            }

            if model.detection.track != nil, model.detection.canControlPlayback {
                playbackControls
                    .frame(maxWidth: .infinity)
                    .transition(.opacity.combined(with: .scale(scale: 0.96)))
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
        let provider = model.detection.providerName ?? "Juke"
        let album = track.album.map { " · \($0)" } ?? ""
        let device = model.detection.playbackDeviceName.map { " · \($0)" } ?? ""
        return "\(track.artist)\(album) · \(provider)\(device)"
    }

    private var playbackControls: some View {
        HStack(spacing: 10) {
            controlButton("Previous track", symbol: "backward.end.fill", prominent: false) {
                await model.detection.previousTrack()
            }
            controlButton(
                model.detection.isPlaying ? "Pause" : "Play",
                symbol: model.detection.isPlaying ? "pause.fill" : "play.fill",
                prominent: true
            ) {
                await model.detection.togglePlayback()
            }
            controlButton("Next track", symbol: "forward.end.fill", prominent: false) {
                await model.detection.nextTrack()
            }
        }
        .animation(.easeInOut(duration: 0.2), value: model.detection.canControlPlayback)
    }

    private func controlButton(
        _ label: String,
        symbol: String,
        prominent: Bool,
        action: @escaping @MainActor () async -> Void
    ) -> some View {
        ResponsivePlaybackButton(
            label: label,
            symbol: symbol,
            tint: model.atmosphere.primary,
            prominent: prominent,
            isBusy: model.detection.isPlaybackBusy,
            action: action
        )
    }

    private var playbackAccessBadge: some View {
        Menu {
            Picker("Listening mode", selection: playbackModeSelection) {
                Label("Spectator mode", systemImage: "eye").tag("spectator")
                Label("Playback mode", systemImage: "play.circle").tag("playback")
            }
            if model.detection.isSpotifySpectatorMode {
                Divider()
                Button("Connect Spotify in Juke…") { model.openSpotifyConnection() }
            }
        } label: {
            Image(systemName: model.detection.isSpotifySpectatorMode ? "eye" : "play.circle")
                .font(.body.weight(.semibold))
                .foregroundStyle(.secondary)
                .frame(width: 30, height: 30)
                .background(.regularMaterial, in: Circle())
                .contentShape(Circle())
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help(playbackModeHelp)
        .accessibilityLabel(model.detection.isSpotifySpectatorMode ? "Spectator mode" : "Playback mode")
        .accessibilityHint(playbackModeHelp)
        .accessibilityIdentifier(
            model.detection.isSpotifySpectatorMode
                ? "nowPlaying.spectatorMode"
                : "nowPlaying.playbackMode"
        )
    }

    private var playbackModeSelection: Binding<String> {
        Binding(
            get: { model.detection.isSpotifySpectatorMode ? "spectator" : "playback" },
            set: { mode in
                if mode == "spectator" { model.useSpotifySpectatorMode() }
                else { model.useSpotifyPlaybackMode() }
            }
        )
    }

    private var playbackModeHelp: String {
        if model.detection.isSpotifySpectatorMode {
            return "Spectator mode is on. If you wish to provide your streaming credentials, click here."
        }
        return "Playback mode is on. Click here to switch to spectator mode."
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
        .menuIndicator(.hidden)
        .fixedSize()
    }

    private func progressRow(at date: Date) -> some View {
        let livePosition = model.detection.estimatedPlaybackPosition(at: date)
        let displayedPosition = isScrubbing ? scrubPosition : livePosition
        return HStack(spacing: 10) {
            Text(format(displayedPosition)).monospacedDigit()
            if model.detection.canControlPlayback {
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
                .disabled(model.detection.isPlaybackBusy)
                .accessibilityLabel("Playback position")
            } else {
                passiveProgress(position: displayedPosition)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("Playback progress")
                    .accessibilityValue("\(format(displayedPosition)) of \(format(model.detection.playbackDuration))")
                    .accessibilityIdentifier("nowPlaying.passiveProgress")
            }
            Text(format(model.detection.playbackDuration)).monospacedDigit()
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
    }

    private func passiveProgress(position: TimeInterval) -> some View {
        GeometryReader { proxy in
            let duration = max(1, model.detection.playbackDuration)
            let fraction = min(1, max(0, position / duration))
            ZStack(alignment: .leading) {
                Capsule().fill(Color.secondary.opacity(0.2)).frame(height: 5)
                Capsule()
                    .fill(model.atmosphere.primary.opacity(0.8))
                    .frame(width: proxy.size.width * fraction, height: 5)
            }
            .frame(maxHeight: .infinity)
        }
        .frame(height: 14)
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

private struct ResponsivePlaybackButton: View {
    let label: String
    let symbol: String
    let tint: Color
    let prominent: Bool
    let isBusy: Bool
    let action: @MainActor () async -> Void

    @State private var isHovered = false

    var body: some View {
        Button { Task { await action() } } label: {
            Image(systemName: symbol)
                .font(prominent ? .title3.weight(.semibold) : .body.weight(.semibold))
                .frame(width: prominent ? 46 : 40, height: prominent ? 46 : 40)
                .contentShape(Circle())
        }
        .buttonStyle(ResponsivePlaybackButtonStyle(
            tint: tint,
            prominent: prominent,
            isHovered: isHovered
        ))
        .disabled(isBusy)
        .onHover { hovering in
            withAnimation(.easeOut(duration: 0.12)) { isHovered = hovering }
        }
        .accessibilityLabel(label)
        .help(label)
    }
}

private struct ResponsivePlaybackButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    let tint: Color
    let prominent: Bool
    let isHovered: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(isEnabled ? .primary : .tertiary)
            .background {
                Circle().fill(backgroundColor(configuration: configuration))
            }
            .overlay {
                Circle().strokeBorder(
                    tint.opacity(isHovered && isEnabled ? 0.5 : 0.16),
                    lineWidth: isHovered ? 1.5 : 1
                )
            }
            .scaleEffect(configuration.isPressed ? 0.91 : (isHovered && isEnabled ? 1.07 : 1))
            .shadow(
                color: tint.opacity(isHovered && isEnabled ? 0.24 : 0),
                radius: isHovered ? 8 : 0
            )
            .animation(.spring(response: 0.2, dampingFraction: 0.72), value: configuration.isPressed)
            .animation(.easeOut(duration: 0.12), value: isHovered)
    }

    private func backgroundColor(configuration: Configuration) -> Color {
        guard isEnabled else { return Color.secondary.opacity(0.06) }
        if configuration.isPressed { return tint.opacity(0.3) }
        if isHovered { return tint.opacity(prominent ? 0.24 : 0.16) }
        return tint.opacity(prominent ? 0.16 : 0.08)
    }
}
