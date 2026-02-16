import SwiftUI

/// A themed gradient background view.
///
/// Uses the current theme's background and panel colors to create a gradient.
/// Dark themes include radial accent gradients; light themes use a solid background.
///
/// ## Usage
///
/// ```swift
/// ZStack {
///     JukeKitBackground()
///     // Your content
/// }
/// .jukeTheme(MyAppTheme())
/// ```
public struct JukeKitBackground: View {
    @Environment(\.jukeTheme) private var theme

    /// Style of background gradient to display.
    public enum Style {
        /// Dark theme style with radial accent gradients.
        case dark
        /// Light theme style with solid background.
        case light
        /// Automatically detect based on theme brightness.
        case automatic
    }

    private let style: Style

    /// Creates a themed background.
    /// - Parameter style: The gradient style. Defaults to `.automatic`.
    public init(style: Style = .automatic) {
        self.style = style
    }

    public var body: some View {
        let isDark = resolveIsDark()

        if isDark {
            darkBackground
        } else {
            lightBackground
        }
    }

    private func resolveIsDark() -> Bool {
        switch style {
        case .dark:
            return true
        case .light:
            return false
        case .automatic:
            // Simple heuristic: check if background is dark
            // by comparing to a threshold
            return isColorDark(theme.background)
        }
    }

    private func isColorDark(_ color: Color) -> Bool {
        // Convert to UIColor to get RGB components
        #if canImport(UIKit)
        let uiColor = UIColor(color)
        var red: CGFloat = 0
        var green: CGFloat = 0
        var blue: CGFloat = 0
        var alpha: CGFloat = 0
        uiColor.getRed(&red, green: &green, blue: &blue, alpha: &alpha)
        // Calculate luminance
        let luminance = 0.299 * red + 0.587 * green + 0.114 * blue
        return luminance < 0.5
        #else
        // On macOS, default to dark
        return true
        #endif
    }

    @ViewBuilder
    private var darkBackground: some View {
        ZStack {
            LinearGradient(
                colors: [theme.background, theme.panel],
                startPoint: .top,
                endPoint: .bottom
            )
            RadialGradient(
                gradient: Gradient(colors: [theme.secondary.opacity(0.3), .clear]),
                center: .topTrailing,
                startRadius: 0,
                endRadius: 400
            )
            RadialGradient(
                gradient: Gradient(colors: [theme.accent.opacity(0.25), .clear]),
                center: .topLeading,
                startRadius: 0,
                endRadius: 350
            )
        }
        .ignoresSafeArea()
    }

    @ViewBuilder
    private var lightBackground: some View {
        theme.background
            .ignoresSafeArea()
    }
}
