import SwiftUI

/// A themed card container with gradient background and subtle shadow.
///
/// Adapts styling based on the current theme (dark vs light).
///
/// ## Usage
///
/// ```swift
/// JukeKitCard {
///     Text("Card content")
/// }
/// ```
public struct JukeKitCard<Content: View>: View {
    @Environment(\.jukeTheme) private var theme

    private let padding: CGFloat
    private let cornerRadius: CGFloat
    private let content: Content

    /// Creates a themed card.
    /// - Parameters:
    ///   - padding: Inner padding. Defaults to 24.
    ///   - cornerRadius: Corner radius. Defaults to 24.
    ///   - content: The card content.
    public init(
        padding: CGFloat = 24,
        cornerRadius: CGFloat = 24,
        @ViewBuilder content: () -> Content
    ) {
        self.padding = padding
        self.cornerRadius = cornerRadius
        self.content = content()
    }

    public var body: some View {
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [theme.panel.opacity(0.95), theme.panelAlt.opacity(0.9)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .stroke(theme.border, lineWidth: 1)
                    )
                    .shadow(color: Color.black.opacity(0.3), radius: 25, x: 0, y: 15)
            )
    }
}
