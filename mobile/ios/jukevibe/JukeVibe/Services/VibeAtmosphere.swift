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

struct VibeBackground: View {
    let atmosphere: VibeAtmosphere
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        ZStack {
            Color(.systemBackground)
            LinearGradient(colors: [atmosphere.secondary.opacity(0.55), atmosphere.primary.opacity(0.24), .clear], startPoint: .topLeading, endPoint: .bottomTrailing)
            Circle().fill(atmosphere.primary.opacity(0.12 + atmosphere.intensity * 0.14)).frame(width: 430).blur(radius: 90).offset(x: 150, y: -260)
        }.animation(reduceMotion ? nil : .easeInOut(duration: 1.5), value: atmosphere.primary).ignoresSafeArea()
    }
}
