import SwiftUI

/// A themed status banner for displaying messages.
///
/// Displays an optional message with a colored indicator dot and background.
/// When the message is nil, the banner is hidden.
///
/// ## Usage
///
/// ```swift
/// JukeCoreStatusBanner(message: errorMessage, variant: .error)
/// ```
public struct JukeCoreStatusBanner: View {
    @Environment(\.jukeTheme) private var theme

    /// Banner style variants.
    public enum Variant {
        case info
        case success
        case warning
        case error
    }

    private let message: String?
    private let variant: Variant

    /// Creates a themed status banner.
    /// - Parameters:
    ///   - message: The message to display. If nil, banner is hidden.
    ///   - variant: The banner variant. Defaults to `.info`.
    public init(message: String?, variant: Variant = .info) {
        self.message = message
        self.variant = variant
    }

    private var palette: (color: Color, background: Color) {
        switch variant {
        case .info:
            return (theme.accent, theme.accent.opacity(0.12))
        case .success:
            return (theme.success, theme.success.opacity(0.18))
        case .warning:
            return (theme.warning, theme.warning.opacity(0.18))
        case .error:
            return (theme.error, theme.error.opacity(0.2))
        }
    }

    public var body: some View {
        Group {
            if let message {
                HStack(alignment: .top, spacing: 12) {
                    Circle()
                        .fill(palette.color)
                        .frame(width: 10, height: 10)
                        .shadow(color: palette.color.opacity(0.65), radius: 8)
                        .padding(.top, 6)
                    Text(message)
                        .foregroundColor(theme.text)
                        .font(.subheadline)
                    Spacer(minLength: 0)
                }
                .padding(.vertical, 12)
                .padding(.horizontal, 16)
                .background(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(palette.background)
                        .overlay(
                            RoundedRectangle(cornerRadius: 18, style: .continuous)
                                .stroke(palette.color.opacity(0.35), lineWidth: 1)
                        )
                )
            }
        }
    }
}
