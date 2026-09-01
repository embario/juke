import SwiftUI

struct NowPlayingBar: View {
    @Environment(AppModel.self) private var model
    @State private var menuPresented = false

    var body: some View {
        HStack(spacing: 12) {
            artwork
            VStack(alignment: .leading, spacing: 2) {
                Text(model.detection.track?.title ?? "Listening for music").font(.headline).lineLimit(1)
                Text(model.detection.track.map { "\($0.artist) · \(model.detection.providerName ?? "Juke Vibe")" } ?? "Spotify and Apple Music metadata are checked quietly")
                    .font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer()
            Circle().fill(model.detection.isAudioPresent ? model.atmosphere.primary : .secondary.opacity(0.35)).frame(width: 8, height: 8)
            Menu {
                Picker("Music detection", selection: Bindable(model.detection).mode) {
                    ForEach(MusicDetectionController.Mode.allCases) { mode in Text(mode.title).tag(mode) }
                }
                Divider()
                Button("Apply detection mode") { Task { await model.detection.start() } }
            } label: { Image(systemName: "ellipsis").frame(width: 28, height: 28) }
            .menuStyle(.borderlessButton).fixedSize()
        }
        .padding(.horizontal, 18).padding(.vertical, 10).background(.ultraThinMaterial)
    }

    @ViewBuilder private var artwork: some View {
        if let url = model.detection.track?.artworkURL {
            AsyncImage(url: url) { image in image.resizable().scaledToFill() } placeholder: { Color.white.opacity(0.08) }
                .frame(width: 42, height: 42).clipShape(RoundedRectangle(cornerRadius: 7))
        } else {
            RoundedRectangle(cornerRadius: 7).fill(model.atmosphere.primary.opacity(0.24)).frame(width: 42, height: 42)
                .overlay(Image(systemName: "waveform").foregroundStyle(model.atmosphere.primary))
        }
    }
}
