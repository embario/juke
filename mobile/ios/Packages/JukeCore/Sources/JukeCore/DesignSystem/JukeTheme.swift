import SwiftUI

/// Protocol defining the color scheme for a Juke app theme.
///
/// Implement this protocol to create a custom theme for your app.
/// The theme colors are used by all JukeCore design system components.
///
/// ## Usage
///
/// ```swift
/// struct MyAppTheme: JukeTheme {
///     let background = Color(hex: "#030712")
///     let panel = Color(hex: "#090f1f")
///     // ... define all required colors
/// }
///
/// // Apply theme to your app
/// ContentView()
///     .environment(\.jukeTheme, MyAppTheme())
/// ```
public protocol JukeTheme {
    // MARK: - Background Colors

    /// Primary background color for the app.
    var background: Color { get }

    /// Panel/card background color.
    var panel: Color { get }

    /// Alternative panel color for nested elements.
    var panelAlt: Color { get }

    // MARK: - Brand Colors

    /// Primary accent color for buttons, links, and highlights.
    var accent: Color { get }

    /// Softer variant of the accent color.
    var accentSoft: Color { get }

    /// Secondary accent color (optional, defaults to accent).
    var secondary: Color { get }

    // MARK: - Text Colors

    /// Primary text color.
    var text: Color { get }

    /// Muted/secondary text color.
    var muted: Color { get }

    // MARK: - Utility Colors

    /// Border/separator color.
    var border: Color { get }

    /// Success state color.
    var success: Color { get }

    /// Warning state color.
    var warning: Color { get }

    /// Error state color.
    var error: Color { get }

    // MARK: - Button Foreground

    /// Foreground color for primary buttons (defaults to panel for dark themes).
    var primaryButtonForeground: Color { get }
}

// MARK: - Default Implementations

public extension JukeTheme {
    var secondary: Color { accent }
    var primaryButtonForeground: Color { panel }
}

// MARK: - Environment Key

/// Environment key for the current JukeTheme.
public struct JukeThemeKey: EnvironmentKey {
    public static let defaultValue: JukeTheme = JukeDefaultTheme()
}

public extension EnvironmentValues {
    /// The current Juke theme for design system components.
    var jukeTheme: JukeTheme {
        get { self[JukeThemeKey.self] }
        set { self[JukeThemeKey.self] = newValue }
    }
}

// MARK: - View Extension

public extension View {
    /// Applies a Juke theme to this view and its descendants.
    func jukeTheme(_ theme: JukeTheme) -> some View {
        environment(\.jukeTheme, theme)
    }
}
