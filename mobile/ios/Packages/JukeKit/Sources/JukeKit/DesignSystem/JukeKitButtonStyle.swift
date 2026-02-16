import SwiftUI

/// A themed button style with multiple variants.
///
/// ## Variants
///
/// - `primary`: Filled button with accent gradient.
/// - `secondary`: Filled button with secondary color.
/// - `ghost`: Transparent button with border.
/// - `link`: Text-only button styled as a link.
/// - `destructive`: Filled button with error color.
///
/// ## Usage
///
/// ```swift
/// Button("Submit") { }
///     .buttonStyle(JukeKitButtonStyle(variant: .primary))
/// ```
public struct JukeKitButtonStyle: ButtonStyle {
    @Environment(\.jukeTheme) private var theme

    /// Button style variants.
    public enum Variant {
        case primary
        case secondary
        case ghost
        case link
        case destructive
    }

    private let variant: Variant
    private let cornerRadius: CGFloat

    /// Creates a themed button style.
    /// - Parameters:
    ///   - variant: The button variant. Defaults to `.primary`.
    ///   - cornerRadius: Corner radius. Defaults to 18.
    public init(variant: Variant = .primary, cornerRadius: CGFloat = 18) {
        self.variant = variant
        self.cornerRadius = cornerRadius
    }

    public func makeBody(configuration: Configuration) -> some View {
        JukeKitButtonStyleBody(
            configuration: configuration,
            variant: variant,
            cornerRadius: cornerRadius,
            theme: theme
        )
    }
}

/// Internal view to work around environment access in ButtonStyle.
private struct JukeKitButtonStyleBody: View {
    let configuration: ButtonStyleConfiguration
    let variant: JukeKitButtonStyle.Variant
    let cornerRadius: CGFloat
    let theme: JukeTheme

    var body: some View {
        configuration.label
            .font(.headline)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .padding(.horizontal, 20)
            .background(background(isPressed: configuration.isPressed))
            .foregroundColor(foregroundColor)
            .overlay(borderOverlay)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
            .opacity(configuration.isPressed ? 0.9 : 1)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.easeInOut(duration: 0.15), value: configuration.isPressed)
    }

    @ViewBuilder
    private func background(isPressed: Bool) -> some View {
        switch variant {
        case .primary:
            LinearGradient(
                colors: [theme.accent, theme.accentSoft],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .brightness(isPressed ? -0.05 : 0)
        case .secondary:
            theme.secondary
                .brightness(isPressed ? -0.05 : 0)
        case .ghost:
            theme.panelAlt.opacity(isPressed ? 0.7 : 0.5)
        case .link:
            Color.clear
        case .destructive:
            theme.error
                .brightness(isPressed ? -0.05 : 0)
        }
    }

    private var foregroundColor: Color {
        switch variant {
        case .primary:
            return theme.primaryButtonForeground
        case .secondary, .destructive:
            return .white
        case .ghost:
            return theme.text
        case .link:
            return theme.accent
        }
    }

    @ViewBuilder
    private var borderOverlay: some View {
        switch variant {
        case .ghost:
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .stroke(theme.border, lineWidth: 1)
        case .primary, .secondary, .link, .destructive:
            EmptyView()
        }
    }
}
