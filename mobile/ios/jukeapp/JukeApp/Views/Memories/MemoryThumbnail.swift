import AVFoundation
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
        if let photo = memory.media.first(where: { $0.kind == "image" }) { return .photo(photo) }
        if let video = memory.media.first(where: { $0.kind == "video" }) { return .video(video) }
        if let url = memory.songs.compactMap(\.artworkURL).first { return .artwork(url) }
        return .placeholder
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
        .frame(width: side, height: side).clipShape(RoundedRectangle(cornerRadius: 10))
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
