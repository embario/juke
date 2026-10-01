import AppKit
import SwiftUI

/// An sRGB colour with 8-bit channels, matching the prototype's hex maths.
///
/// Theme tokens are computed in this space (not SwiftUI `Color`) so they can be
/// mixed, compared and contrast-checked exactly like the design reference.
struct RGB: Hashable, Sendable, CustomStringConvertible {
    let r: UInt8
    let g: UInt8
    let b: UInt8

    init(_ r: UInt8, _ g: UInt8, _ b: UInt8) {
        self.r = r
        self.g = g
        self.b = b
    }

    /// `"#RRGGBB"`; anything else becomes black.
    init(hex: String) {
        let digits = hex.hasPrefix("#") ? String(hex.dropFirst()) : hex
        let value = digits.count == 6 ? UInt32(digits, radix: 16) ?? 0 : 0
        self.init(UInt8((value >> 16) & 0xFF), UInt8((value >> 8) & 0xFF), UInt8(value & 0xFF))
    }

    /// Channels in 0...1.
    init(red: Double, green: Double, blue: Double) {
        func byte(_ value: Double) -> UInt8 { UInt8((min(1, max(0, value)) * 255).rounded()) }
        self.init(byte(red), byte(green), byte(blue))
    }

    var hex: String { String(format: "#%02X%02X%02X", r, g, b) }
    var description: String { hex }

    var red: Double { Double(r) / 255 }
    var green: Double { Double(g) / 255 }
    var blue: Double { Double(b) / 255 }

    /// Port of the prototype's `mix(a, b, t)`: per-channel linear blend in
    /// gamma-encoded sRGB, rounded to the nearest byte.
    func mix(_ other: RGB, _ t: Double) -> RGB {
        func blend(_ a: UInt8, _ b: UInt8) -> UInt8 {
            UInt8((Double(a) * (1 - t) + Double(b) * t).rounded())
        }
        return RGB(blend(r, other.r), blend(g, other.g), blend(b, other.b))
    }

    /// WCAG 2.x relative luminance.
    var relativeLuminance: Double {
        func linear(_ channel: Double) -> Double {
            channel <= 0.04045 ? channel / 12.92 : pow((channel + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)
    }

    /// WCAG contrast ratio between two opaque colours (1...21).
    static func contrast(_ a: RGB, _ b: RGB) -> Double {
        let (light, dark) = a.relativeLuminance >= b.relativeLuminance ? (a, b) : (b, a)
        return (light.relativeLuminance + 0.05) / (dark.relativeLuminance + 0.05)
    }

    /// Hue (0..<360), saturation and lightness (0...1).
    var hsl: (h: Double, s: Double, l: Double) {
        let maxValue = max(red, green, blue), minValue = min(red, green, blue)
        let l = (maxValue + minValue) / 2
        let delta = maxValue - minValue
        guard delta > 0 else { return (0, 0, l) }
        let s = delta / (1 - abs(2 * l - 1))
        var h: Double
        switch maxValue {
        case red: h = ((green - blue) / delta).truncatingRemainder(dividingBy: 6)
        case green: h = (blue - red) / delta + 2
        default: h = (red - green) / delta + 4
        }
        h *= 60
        if h < 0 { h += 360 }
        return (h, s, l)
    }

    init(hue: Double, saturation: Double, lightness: Double) {
        let c = (1 - abs(2 * lightness - 1)) * saturation
        let x = c * (1 - abs((hue / 60).truncatingRemainder(dividingBy: 2) - 1))
        let m = lightness - c / 2
        let (r1, g1, b1): (Double, Double, Double) = switch hue {
        case ..<60: (c, x, 0)
        case ..<120: (x, c, 0)
        case ..<180: (0, c, x)
        case ..<240: (0, x, c)
        case ..<300: (x, 0, c)
        default: (c, 0, x)
        }
        self.init(red: r1 + m, green: g1 + m, blue: b1 + m)
    }

    /// A colour over another at the given alpha (for tokens like `line`).
    func composited(over background: RGB, alpha: Double) -> RGB { background.mix(self, alpha) }

    var color: Color { Color(.sRGB, red: red, green: green, blue: blue, opacity: 1) }
    func color(opacity: Double) -> Color { Color(.sRGB, red: red, green: green, blue: blue, opacity: opacity) }
    var nsColor: NSColor { NSColor(srgbRed: red, green: green, blue: blue, alpha: 1) }

    init?(nsColor: NSColor) {
        guard let srgb = nsColor.usingColorSpace(.sRGB) else { return nil }
        self.init(red: srgb.redComponent, green: srgb.greenComponent, blue: srgb.blueComponent)
    }
}
