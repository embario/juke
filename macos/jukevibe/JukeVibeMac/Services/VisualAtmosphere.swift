import AppKit
import CoreImage
import Foundation
import Observation
import SwiftUI

@MainActor
@Observable
final class VisualAtmosphere {
    var primary = Color(red: 0.31, green: 0.25, blue: 0.55)
    var secondary = Color(red: 0.08, green: 0.24, blue: 0.29)
    var energy: Double = 0.22
    var isEnabled: Bool {
        didSet { UserDefaults.standard.set(isEnabled, forKey: "vibe.visualAtmosphereEnabled") }
    }

    @ObservationIgnored private var artworkTask: Task<Void, Never>?
    @ObservationIgnored private var currentArtworkURL: URL?

    init() {
        isEnabled = UserDefaults.standard.object(forKey: "vibe.visualAtmosphereEnabled") as? Bool ?? true
    }

    func update(track: RecognizedTrack?, isAudioPresent: Bool) {
        energy = isEnabled ? (isAudioPresent ? 0.72 : (track == nil ? 0.16 : 0.4)) : 0.08
        guard isEnabled, let url = track?.artworkURL, url != currentArtworkURL else {
            if track == nil { resetPalette() }
            return
        }
        currentArtworkURL = url
        artworkTask?.cancel()
        artworkTask = Task { [weak self] in
            guard let requestURL = self?.currentArtworkURL else { return }
            do {
                let (data, _) = try await URLSession.shared.data(from: requestURL)
                guard !Task.isCancelled, data.count < 12_000_000,
                      let image = NSImage(data: data),
                      let color = Self.averageColor(image) else { return }
                self?.apply(color)
            } catch { }
        }
    }

    private func apply(_ color: NSColor) {
        let rgb = color.usingColorSpace(.sRGB) ?? color
        primary = Color(nsColor: rgb.blended(withFraction: 0.16, of: .white) ?? rgb)
        secondary = Color(nsColor: rgb.blended(withFraction: 0.58, of: .black) ?? rgb)
    }

    private func resetPalette() {
        primary = Color(red: 0.31, green: 0.25, blue: 0.55)
        secondary = Color(red: 0.08, green: 0.24, blue: 0.29)
    }

    nonisolated private static func averageColor(_ image: NSImage) -> NSColor? {
        guard let data = image.tiffRepresentation, let input = CIImage(data: data) else { return nil }
        let extent = input.extent
        guard let filter = CIFilter(name: "CIAreaAverage", parameters: [kCIInputImageKey: input, kCIInputExtentKey: CIVector(cgRect: extent)]),
              let output = filter.outputImage else { return nil }
        var bitmap = [UInt8](repeating: 0, count: 4)
        CIContext(options: [.workingColorSpace: NSNull()]).render(
            output,
            toBitmap: &bitmap,
            rowBytes: 4,
            bounds: CGRect(x: 0, y: 0, width: 1, height: 1),
            format: .RGBA8,
            colorSpace: CGColorSpaceCreateDeviceRGB()
        )
        return NSColor(red: CGFloat(bitmap[0]) / 255, green: CGFloat(bitmap[1]) / 255, blue: CGFloat(bitmap[2]) / 255, alpha: 1)
    }
}

struct VibeAtmosphereBackground: View {
    let atmosphere: VisualAtmosphere
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ZStack {
            Color(nsColor: .windowBackgroundColor)
            LinearGradient(
                colors: [atmosphere.secondary.opacity(0.48), atmosphere.primary.opacity(0.28), .clear],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            Circle()
                .fill(atmosphere.primary.opacity(0.14 + atmosphere.energy * 0.16))
                .blur(radius: 95)
                .frame(width: 520, height: 520)
                .offset(x: 240, y: -210)
                .scaleEffect(reduceMotion ? 1 : 0.96 + atmosphere.energy * 0.08)
        }
        .animation(reduceMotion ? nil : .easeInOut(duration: 1.8), value: atmosphere.primary)
        .animation(reduceMotion ? nil : .easeInOut(duration: 1.0), value: atmosphere.energy)
        .ignoresSafeArea()
    }
}
