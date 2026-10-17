import CoreImage
import Observation
import SwiftUI
import UIKit

@MainActor
@Observable
final class VibeAtmosphere {
    var primary = Color(red: 0.42, green: 0.34, blue: 0.72)
    var secondary = Color(red: 0.08, green: 0.2, blue: 0.26)
    var intensity = 0.2
    var enabled = true
    private var task: Task<Void, Never>?

    func update(for track: NowPlayingTrack?) {
        intensity = enabled && track != nil ? 0.66 : 0.18
        guard enabled, let track else { return }
        if let image = track.localArtwork { apply(image) }
        else if let url = track.artworkURL {
            task?.cancel(); task = Task { [weak self] in
                if let (data, _) = try? await URLSession.shared.data(from: url), let image = UIImage(data: data) { self?.apply(image) }
            }
        }
    }

    private func apply(_ image: UIImage) {
        guard let input = CIImage(image: image), let filter = CIFilter(name: "CIAreaAverage", parameters: [kCIInputImageKey: input, kCIInputExtentKey: CIVector(cgRect: input.extent)]), let output = filter.outputImage else { return }
        var rgba = [UInt8](repeating: 0, count: 4)
        CIContext().render(output, toBitmap: &rgba, rowBytes: 4, bounds: CGRect(x: 0, y: 0, width: 1, height: 1), format: .RGBA8, colorSpace: CGColorSpaceCreateDeviceRGB())
        let color = UIColor(red: CGFloat(rgba[0]) / 255, green: CGFloat(rgba[1]) / 255, blue: CGFloat(rgba[2]) / 255, alpha: 1)
        primary = Color(uiColor: color); secondary = Color(uiColor: color.withAlphaComponent(1)).opacity(0.48)
    }
}

/// The page background: the themed page colour plus two soft glows in the current
/// artwork colour. The theme (and so the glows) cross-fades whenever the artwork
/// changes; Reduce Motion swaps instantly.
struct VibeBackground: View {
    let atmosphere: VibeAtmosphere
    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let glow = VibeBackgroundGlow.opacity(dark: theme.isDark, intensity: atmosphere.intensity)
        ZStack {
            theme.bg.color
            // Overlays, so the oversized glows never widen the layout past the screen.
            Color.clear.overlay { Circle().fill(theme.base.color.opacity(glow.primary)).frame(width: 430, height: 430).blur(radius: 90).offset(x: 150, y: -260) }
            Color.clear.overlay { Circle().fill(theme.base.color.opacity(glow.secondary)).frame(width: 360, height: 360).blur(radius: 100).offset(x: -170, y: 300) }
        }
        .clipped()
        .animation(reduceMotion ? nil : .easeInOut(duration: 1.1), value: theme.base)
        .animation(reduceMotion ? nil : .easeInOut(duration: 1.1), value: theme.isDark)
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }
}

enum VibeBackgroundGlow {
    /// Glow strength. Text is ink on page colour, so glows stay soft enough to keep
    /// contrast; the theme's own tint already guarantees AA for the base page colour.
    static func opacity(dark: Bool, intensity: Double) -> (primary: Double, secondary: Double) {
        let t = min(1, max(0, intensity))
        let peak = dark ? 0.42 : 0.30
        return (peak * (0.45 + 0.55 * t), peak * 0.6 * (0.45 + 0.55 * t))
    }
}
