import AVFoundation
import AVKit
import ImageIO
import SwiftUI
import UIKit

/// What a memory row shows as its picture: its own photo, then a video frame, then the song's artwork.
enum MemoryThumbnailChoice: Equatable {
    case photo(MemoryMedia)
    case video(MemoryMedia)
    case artwork(URL)
    case placeholder

    static func choose(for memory: MusicMemory) -> Self {
        if let photo = memory.media.first(where: { $0.kind == "photo" || $0.kind == "image" }) { return .photo(photo) }
        if let video = memory.media.first(where: { $0.kind == "video" }) { return .video(video) }
        if let url = memory.songs.compactMap(\.artworkURL).first { return .artwork(url) }
        return .placeholder
    }

    var viewerItem: MemoryImageViewerItem? {
        switch self {
        case .photo(let media), .video(let media): .attachment(media)
        case .artwork(let url): .artwork(url)
        case .placeholder: nil
        }
    }
}

enum MemoryImageViewerItem: Identifiable, Equatable {
    case attachment(MemoryMedia)
    case artwork(URL)

    var id: String {
        switch self {
        case .attachment(let media): "attachment-\(media.id.uuidString)"
        case .artwork(let url): "artwork-\(url.absoluteString)"
        }
    }

    var isVideo: Bool {
        if case .attachment(let media) = self { return media.kind == "video" }
        return false
    }
}

enum MemoryImageDecoder {
    /// A small decoded image from a local file, so long lists do not hold full-size photos.
    static func downsampled(_ url: URL, maxPixel: CGFloat) -> UIImage? {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, [kCGImageSourceShouldCache: false] as CFDictionary) else { return nil }
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceShouldCacheImmediately: true, kCGImageSourceThumbnailMaxPixelSize: maxPixel,
        ]
        return CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary).map { UIImage(cgImage: $0) }
    }

    static func videoFrame(_ url: URL, maxPixel: CGFloat) async -> UIImage? {
        let generator = AVAssetImageGenerator(asset: AVURLAsset(url: url))
        generator.appliesPreferredTrackTransform = true
        generator.maximumSize = CGSize(width: maxPixel, height: maxPixel)
        return (try? await generator.image(at: .zero)).map { UIImage(cgImage: $0.image) }
    }
}

/// Square thumbnail for a memory in a list.
struct MemoryThumbnail: View {
    @Environment(VibeAppModel.self) private var model
    let memory: MusicMemory
    var side: CGFloat = 56
    var cornerRadius: CGFloat = 10
    @State private var image: UIImage?

    private var choice: MemoryThumbnailChoice { .choose(for: memory) }

    var body: some View {
        ZStack {
            Color.secondary.opacity(0.15)
            if let image { Image(uiImage: image).resizable().scaledToFill() }
            else if case .artwork(let url) = choice {
                AsyncImage(url: url) { $0.resizable().scaledToFill() } placeholder: { Image(systemName: "music.note").foregroundStyle(.secondary) }
            } else { Image(systemName: icon).foregroundStyle(.secondary) }
            if case .video = choice, image != nil { Image(systemName: "play.fill").font(.caption).foregroundStyle(.white).shadow(radius: 2) }
        }
        .frame(width: side, height: side).clipShape(RoundedRectangle(cornerRadius: cornerRadius))
        .accessibilityHidden(true)
        .task(id: choice) { await load() }
    }

    private var icon: String {
        switch choice { case .video: "video"; case .photo: "photo"; default: "photo.on.rectangle.angled" }
    }

    private func load() async {
        image = nil
        let pixels = side * 3
        switch choice {
        case .photo(let media):
            if let url = try? await model.memories.localMediaURL(media) { image = MemoryImageDecoder.downsampled(url, maxPixel: pixels) }
        case .video(let media):
            if let url = try? await model.memories.localMediaURL(media) { image = await MemoryImageDecoder.videoFrame(url, maxPixel: pixels) }
        case .artwork, .placeholder: break
        }
    }
}

/// Full-screen photo viewer shared by the deck and memory detail. Videos open in the same
/// presentation and play immediately; music artwork remains viewable when it is the fallback.
struct MemoryFullscreenViewer: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let item: MemoryImageViewerItem
    @State private var image: UIImage?
    @State private var player: AVPlayer?
    @State private var failed = false

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Color.black.ignoresSafeArea()
            content
            Button("Done", systemImage: "xmark") { dismiss() }
                .labelStyle(.iconOnly)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 44, height: 44)
                .background(.ultraThinMaterial, in: Circle())
                .padding(.top, 12)
                .padding(.trailing, 16)
                .accessibilityLabel("Close image viewer")
                .accessibilityIdentifier("memory.imageViewer.close")
        }
        .task(id: item.id) { await load() }
        .onDisappear { player?.pause() }
    }

    @ViewBuilder
    private var content: some View {
        switch item {
        case .artwork(let url):
            AsyncImage(url: url) { phase in
                if let image = phase.image {
                    image.resizable().scaledToFit().accessibilityIdentifier("memory.imageViewer.image")
                } else if phase.error != nil {
                    failure
                } else {
                    ProgressView().tint(.white)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        case .attachment(let media) where media.kind == "video":
            if let player {
                VideoPlayer(player: player).ignoresSafeArea().accessibilityIdentifier("memory.imageViewer.video")
            } else if failed {
                failure
            } else {
                ProgressView().tint(.white)
            }
        case .attachment:
            if let image {
                Image(uiImage: image).resizable().scaledToFit().accessibilityIdentifier("memory.imageViewer.image")
            } else if failed {
                failure
            } else {
                ProgressView().tint(.white)
            }
        }
    }

    private var failure: some View {
        Text("This image couldn’t be opened.")
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @MainActor
    private func load() async {
        image = nil
        player?.pause()
        player = nil
        failed = false
        do {
            switch item {
            case .artwork:
                return // AsyncImage handles the remote or local artwork URL.
            case .attachment(let media):
                let url = try await model.memories.localMediaURL(media)
                if media.kind == "video" {
                    let next = AVPlayer(url: url)
                    player = next
                    next.play()
                } else {
                    image = MemoryImageDecoder.downsampled(url, maxPixel: 4096)
                    failed = image == nil
                }
            }
        } catch {
            failed = true
        }
    }
}
