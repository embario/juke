import AppKit
import CoreGraphics

extension ArtworkPalette {
    /// The dominant colour of an image already in memory (memory photos).
    nonisolated static func averageColor(_ image: NSImage) -> NSColor? {
        var rect = CGRect(origin: .zero, size: image.size)
        guard let cgImage = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else { return nil }
        return dominantColor(of: cgImage)?.nsColor
    }
}
