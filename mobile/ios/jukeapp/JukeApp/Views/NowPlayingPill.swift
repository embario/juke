import SwiftUI

struct NowPlayingPill: View {
    @Environment(VibeAppModel.self) private var model
    var body: some View {
        HStack(spacing: 11) {
            artwork
            VStack(alignment: .leading, spacing: 2) {
                Text(model.nowPlaying.track?.title ?? "Listening for music").font(.subheadline.bold()).lineLimit(1)
                Text(model.nowPlaying.track.map { "\($0.artist) · \($0.source)" } ?? model.nowPlaying.status).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer()
            Menu {
                Button(model.nowPlaying.isListeningAroundMe ? "Stop Around Me" : "Identify Around Me") { Task { await model.nowPlaying.setAroundMe(!model.nowPlaying.isListeningAroundMe) } }
                Text("Apple Music and connected Spotify playback are checked automatically while Juke is active.")
            } label: { Image(systemName: "ellipsis.circle").font(.title3) }
        }.padding(10).background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 18)).padding(.horizontal).padding(.bottom, 4)
    }

    @ViewBuilder private var artwork: some View {
        if let image = model.nowPlaying.track?.localArtwork { Image(uiImage: image).resizable().scaledToFill().frame(width: 42, height: 42).clipShape(RoundedRectangle(cornerRadius: 8)) }
        else if let url = model.nowPlaying.track?.artworkURL { AsyncImage(url: url) { $0.resizable().scaledToFill() } placeholder: { Color.secondary.opacity(0.15) }.frame(width: 42, height: 42).clipShape(RoundedRectangle(cornerRadius: 8)) }
        else { RoundedRectangle(cornerRadius: 8).fill(model.atmosphere.primary.opacity(0.2)).frame(width: 42, height: 42).overlay(Image(systemName: "waveform")) }
    }
}
