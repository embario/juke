import CoreGraphics
import Foundation
import ImageIO
import Observation
import SwiftUI

/// Extracts a base colour from album art and publishes it for `JukeTheme`.
///
/// The root view builds the theme from `base`; changing artwork cross-fades
/// card, page and well colours over `JukeMotion.colorCrossfade`. Screens can
/// call `update(artworkURL:)` (the app does this for the detected track) or
/// `apply(_:)` when they already hold a colour.
@MainActor
@Observable
final class ArtworkPalette {
    private(set) var base: RGB = JukeTheme.neutralBase

    @ObservationIgnored private var currentURL: URL?
    @ObservationIgnored private var task: Task<Void, Never>?
    @ObservationIgnored private var cache: [URL: RGB] = [:]
    @ObservationIgnored private let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    /// Follows the given artwork. `nil` (or `enabled == false`) returns to the
    /// neutral palette.
    func update(artworkURL: URL?, enabled: Bool = true) {
        guard enabled, let artworkURL else {
            currentURL = nil
            task?.cancel()
            apply(JukeTheme.neutralBase)
            return
        }
        guard artworkURL != currentURL else { return }
        currentURL = artworkURL
        task?.cancel()
        if let cached = cache[artworkURL] {
            apply(cached)
            return
        }
        task = Task { [weak self, session] in
            let data = try? await Self.load(artworkURL, session: session)
            let color: RGB? = if let data {
                await Task.detached(priority: .utility) { Self.dominantColor(imageData: data) }.value
            } else { nil }
            guard let self, !Task.isCancelled, self.currentURL == artworkURL else { return }
            guard let color else {
                // Failed to load or decode: go neutral and let the same URL retry later.
                self.currentURL = nil
                self.apply(JukeTheme.neutralBase)
                return
            }
            if self.cache.count > 64 { self.cache.removeAll() }
            self.cache[artworkURL] = color
            self.apply(color)
        }
    }

    /// Sets the base colour directly, animated like a track change.
    func apply(_ color: RGB) {
        guard color != base else { return }
        withAnimation(JukeMotion.colorCrossfade(reduceMotion: JukeMotion.systemPrefersReducedMotion)) {
            base = color
        }
    }

    private nonisolated static func load(_ url: URL, session: URLSession) async throws -> Data {
        if url.isFileURL { return try Data(contentsOf: url) }
        let (data, response) = try await session.data(from: url)
        guard data.count < 12_000_000, (response as? HTTPURLResponse)?.statusCode ?? 200 == 200 else {
            throw URLError(.badServerResponse)
        }
        return data
    }

    // MARK: Extraction

    nonisolated static func dominantColor(imageData: Data) -> RGB? {
        guard let source = CGImageSourceCreateWithData(imageData as CFData, nil) else { return nil }
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceThumbnailMaxPixelSize: 48,
            kCGImageSourceCreateThumbnailWithTransform: true,
        ]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else { return nil }
        return dominantColor(of: image)
    }

    /// The most prominent colour that is not near-white, near-black or grey,
    /// weighted by saturation squared, then kept in a lightness band that
    /// both palettes can tint with.
    ///
    /// Pixels are bucketed at 4 bits per channel; the winning bucket's pixels
    /// are averaged. If the art is entirely white/black/grey the plain average
    /// is used instead.
    nonisolated static func dominantColor(of image: CGImage) -> RGB? {
        let side = 32
        var pixels = [UInt8](repeating: 0, count: side * side * 4)
        guard let space = CGColorSpace(name: CGColorSpace.sRGB) else { return nil }
        let drawn = pixels.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(
                data: buffer.baseAddress, width: side, height: side, bitsPerComponent: 8, bytesPerRow: side * 4,
                space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
            ) else { return false }
            context.interpolationQuality = .medium
            context.draw(image, in: CGRect(x: 0, y: 0, width: side, height: side))
            return true
        }
        guard drawn else { return nil }

        struct Bucket { var weight = 0.0; var r = 0.0; var g = 0.0; var b = 0.0; var count = 0.0 }
        var buckets: [Int: Bucket] = [:]
        var total = Bucket()
        for index in stride(from: 0, to: pixels.count, by: 4) {
            let alpha = Double(pixels[index + 3]) / 255
            guard alpha > 0.5 else { continue }
            let rgb = RGB(
                UInt8(min(255, Double(pixels[index]) / alpha)),
                UInt8(min(255, Double(pixels[index + 1]) / alpha)),
                UInt8(min(255, Double(pixels[index + 2]) / alpha))
            )
            total.r += rgb.red; total.g += rgb.green; total.b += rgb.blue; total.count += 1
            let hsl = rgb.hsl
            // Skip near-white, near-black and greys, so a colourful area wins
            // even when it is smaller.
            guard hsl.l > 0.1, hsl.l < 0.9, hsl.s > 0.2 else { continue }
            let key = Int(rgb.r >> 4) << 8 | Int(rgb.g >> 4) << 4 | Int(rgb.b >> 4)
            var bucket = buckets[key, default: Bucket()]
            bucket.weight += hsl.s * hsl.s
            bucket.r += rgb.red; bucket.g += rgb.green; bucket.b += rgb.blue; bucket.count += 1
            buckets[key] = bucket
        }
        let chosen = buckets.values.max { $0.weight < $1.weight } ?? total
        guard chosen.count > 0 else { return nil }
        let average = RGB(red: chosen.r / chosen.count, green: chosen.g / chosen.count, blue: chosen.b / chosen.count)
        return usable(average)
    }

    /// Keeps lightness in 0.22...0.78 so neither palette tints towards pure
    /// white or black, preserving hue and saturation.
    nonisolated static func usable(_ color: RGB) -> RGB {
        let hsl = color.hsl
        let lightness = min(0.78, max(0.22, hsl.l))
        guard lightness != hsl.l else { return color }
        return RGB(hue: hsl.h, saturation: hsl.s, lightness: lightness)
    }
}
