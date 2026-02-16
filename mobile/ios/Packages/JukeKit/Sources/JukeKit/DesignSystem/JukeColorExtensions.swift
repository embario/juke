import SwiftUI

extension Color {
    /// Creates a Color from a hex string (e.g., "#FF5733" or "FF5733").
    ///
    /// Supports 3-character and 6-character hex codes.
    ///
    /// - Parameter hex: The hex color string, with or without '#' prefix.
    public init(hex: String) {
        let hexValue = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hexValue).scanHexInt64(&int)
        let r, g, b: UInt64
        switch hexValue.count {
        case 6:
            (r, g, b) = ((int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF)
        case 3:
            let divisor: UInt64 = 17
            (r, g, b) = ((int >> 8) * divisor, (int >> 4 & 0xF) * divisor, (int & 0xF) * divisor)
        default:
            (r, g, b) = (1, 1, 1)
        }
        self.init(.sRGB, red: Double(r) / 255, green: Double(g) / 255, blue: Double(b) / 255)
    }
}
