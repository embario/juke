import SwiftUI

// MARK: - Juke Default Theme (Orange/Dark)

/// The default Juke app theme with orange accents on a dark background.
public struct JukeDefaultTheme: JukeTheme {
    public init() {}

    public let background = Color(hex: "#030712")
    public let panel = Color(hex: "#090f1f")
    public let panelAlt = Color(hex: "#0f172a")
    public let accent = Color(hex: "#f97316")
    public let accentSoft = Color(hex: "#fb923c")
    public let secondary = Color(hex: "#f97316")
    public let text = Color(hex: "#e2e8f0")
    public let muted = Color(hex: "#94a3b8")
    public let border = Color.white.opacity(0.08)
    public let success = Color(hex: "#16a34a")
    public let warning = Color(hex: "#facc15")
    public let error = Color(hex: "#ef4444")
    public let primaryButtonForeground = Color(hex: "#0f172a")
}

// MARK: - ShotClock Theme (Pink/Purple Dark)

/// ShotClock app theme with pink/magenta accents on a dark purple background.
public struct ShotClockTheme: JukeTheme {
    public init() {}

    public let background = Color(hex: "#0A0118")
    public let panel = Color(hex: "#140B2E")
    public let panelAlt = Color(hex: "#1E1145")
    public let accent = Color(hex: "#E11D89")
    public let accentSoft = Color(hex: "#F472B6")
    public let secondary = Color(hex: "#06B6D4")
    public let text = Color(hex: "#F8FAFC")
    public let muted = Color(hex: "#94A3B8")
    public let border = Color.white.opacity(0.06)
    public let success = Color(hex: "#10B981")
    public let warning = Color(hex: "#FBBF24")
    public let error = Color(hex: "#F43F5E")
    public let primaryButtonForeground = Color.white
}

// MARK: - TuneTrivia Theme (Coral/Light)

/// TuneTrivia app theme with coral accents on a light cream background.
public struct TuneTriviaTheme: JukeTheme {
    public init() {}

    public let background = Color(hex: "#faf8f5")
    public let panel = Color(hex: "#fff5eb")
    public let panelAlt = Color(hex: "#ffffff")
    public let accent = Color(hex: "#ff6b6b")
    public let accentSoft = Color(hex: "#ff8e8e")
    public let secondary = Color(hex: "#4ecdc4")
    public let text = Color(hex: "#2d3436")
    public let muted = Color(hex: "#636e72")
    public let border = Color.black.opacity(0.06)
    public let success = Color(hex: "#4ecdc4")
    public let warning = Color(hex: "#ffe66d")
    public let error = Color(hex: "#ff6b6b")
    public let primaryButtonForeground = Color.white
}
