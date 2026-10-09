#if DEBUG
import AVFoundation
import UIKit

/// Sample memories for UI checks (`--uitesting --uitesting-memories-sample`): a photo, a video, song artwork only, and nothing.
nonisolated enum MemorySampleData {
    static func make() async -> (memories: [MusicMemory], media: [(MemoryMedia, Data)]) {
        let photo = MemoryMedia(id: UUID(), kind: "image", filename: "IMG_0412.jpg", contentType: "image/jpeg", url: "")
        let video = MemoryMedia(id: UUID(), kind: "video", filename: "IMG_0413.mov", contentType: "video/quicktime", url: "")
        var media: [(MemoryMedia, Data)] = [(photo, image(.systemTeal, symbol: "sun.max.fill").jpegData(compressionQuality: 0.8) ?? Data())]
        if let clip = await clip(color: .systemIndigo) { media.append((video, clip)) }
        let artwork = artworkFile()
        func song(_ title: String, art: URL?) -> MemorySong {
            // Valid Spotify ids, so playing a sample memory works against the playback fixtures.
            let id = "0aWMVrwxPNYkKmFthzm" + String(format: "%03d", title.unicodeScalars.reduce(0) { ($0 * 31 + Int($1.value)) % 1000 })
            var song = MemorySong(title: title, artist: "Miles Davis", provider: "spotify", providerID: id)
            song.artworkURL = art
            return song
        }
        func memory(_ title: String, daysAgo: Int, songs: [MemorySong], media: [MemoryMedia], text: String = "", place: String = "", people: [String] = [], tags: [String] = [], suggested: [String] = []) -> MusicMemory {
            let date = Date().addingTimeInterval(TimeInterval(-86_400 * daysAgo))
            var memory = MusicMemory(id: UUID(), title: title, text: text, occurredAt: date, createdAt: date, place: place, people: people, songs: songs, media: media, tags: tags, classification: .unavailable)
            memory.generatedTags = suggested
            return memory
        }
        return ([
            memory("Beach with the family", daysAgo: 1, songs: [song("Blue in Green", art: artwork)], media: [photo],
                   text: "Windows down on the drive out, the whole car quiet for the bridge. Sand in everything by noon.", place: "Rockaway", people: ["Sam", "Priya"],
                   tags: ["summer", "family"], suggested: ["beach", "road trip", "family"]),
            memory("Sunday drive", daysAgo: 2, songs: [song("So What", art: artwork)], media: media.count > 1 ? [video] : []),
            memory("Late night listening", daysAgo: 3, songs: [song("Freddie Freeloader", art: artwork)], media: []),
            memory("A quiet note", daysAgo: 4, songs: [], media: []),
        ], media)
    }

    private static func image(_ color: UIColor, symbol: String) -> UIImage {
        UIGraphicsImageRenderer(size: CGSize(width: 600, height: 600)).image { context in
            color.setFill(); context.fill(CGRect(x: 0, y: 0, width: 600, height: 600))
            let glyph = UIImage(systemName: symbol, withConfiguration: UIImage.SymbolConfiguration(pointSize: 240))?.withTintColor(.white, renderingMode: .alwaysOriginal)
            glyph?.draw(at: CGPoint(x: 300 - (glyph?.size.width ?? 0) / 2, y: 300 - (glyph?.size.height ?? 0) / 2))
        }
    }

    private static func artworkFile() -> URL? {
        let url = FileManager.default.temporaryDirectory.appending(path: "sample-artwork.png")
        try? image(.systemOrange, symbol: "music.note").pngData()?.write(to: url)
        return url
    }

    private static func clip(color: UIColor) async -> Data? {
        let url = FileManager.default.temporaryDirectory.appending(path: "sample-clip.mov")
        try? FileManager.default.removeItem(at: url)
        guard let writer = try? AVAssetWriter(outputURL: url, fileType: .mov) else { return nil }
        let size = 320
        let input = AVAssetWriterInput(mediaType: .video, outputSettings: [AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: size, AVVideoHeightKey: size])
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB])
        writer.add(input)
        guard writer.startWriting() else { return nil }
        writer.startSession(atSourceTime: .zero)
        let frame = image(color, symbol: "figure.walk")
        for index in 0..<2 {
            while !input.isReadyForMoreMediaData { try? await Task.sleep(for: .milliseconds(10)) }
            var buffer: CVPixelBuffer?
            CVPixelBufferCreate(nil, size, size, kCVPixelFormatType_32ARGB, nil, &buffer)
            guard let buffer, let cg = frame.cgImage else { return nil }
            CVPixelBufferLockBaseAddress(buffer, [])
            let context = CGContext(data: CVPixelBufferGetBaseAddress(buffer), width: size, height: size, bitsPerComponent: 8, bytesPerRow: CVPixelBufferGetBytesPerRow(buffer),
                                    space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue)
            context?.draw(cg, in: CGRect(x: 0, y: 0, width: size, height: size))
            CVPixelBufferUnlockBaseAddress(buffer, [])
            adaptor.append(buffer, withPresentationTime: CMTime(value: CMTimeValue(index), timescale: 1))
        }
        input.markAsFinished()
        await writer.finishWriting()
        return try? Data(contentsOf: url)
    }
}
#endif
