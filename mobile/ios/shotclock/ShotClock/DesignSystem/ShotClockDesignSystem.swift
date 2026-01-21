import SwiftUI
import UIKit

// MARK: - Tokens

enum SCPalette {
    static let background = Color(hex: "#0A0118")
    static let panel = Color(hex: "#140B2E")
    static let panelAlt = Color(hex: "#1E1145")
    static let accent = Color(hex: "#E11D89")
    static let accentSoft = Color(hex: "#F472B6")
    static let secondary = Color(hex: "#06B6D4")
    static let text = Color(hex: "#F8FAFC")
    static let muted = Color(hex: "#94A3B8")
    static let border = Color.white.opacity(0.06)
    static let success = Color(hex: "#10B981")
    static let warning = Color(hex: "#FBBF24")
    static let error = Color(hex: "#F43F5E")
}

extension Color {
    init(hex: String) {
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

// MARK: - Background

struct SCBackground: View {
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [SCPalette.background, SCPalette.panel],
                startPoint: .top,
                endPoint: .bottom
            )
            RadialGradient(
                gradient: Gradient(colors: [SCPalette.accent.opacity(0.2), .clear]),
                center: .topLeading,
                startRadius: 0,
                endRadius: 350
            )
            RadialGradient(
                gradient: Gradient(colors: [SCPalette.secondary.opacity(0.15), .clear]),
                center: .bottomTrailing,
                startRadius: 0,
                endRadius: 400
            )
        }
        .ignoresSafeArea()
    }
}

// MARK: - Card

struct SCCard<Content: View>: View {
    private let padding: CGFloat
    private let content: Content

    init(padding: CGFloat = 20, @ViewBuilder content: () -> Content) {
        self.padding = padding
        self.content = content()
    }

    var body: some View {
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [SCPalette.panel.opacity(0.95), SCPalette.panelAlt.opacity(0.9)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .stroke(SCPalette.border, lineWidth: 1)
                    )
                    .shadow(color: Color.black.opacity(0.4), radius: 20, x: 0, y: 12)
            )
    }
}

// MARK: - Button Styles

struct SCButtonStyle: ButtonStyle {
    enum Variant {
        case primary
        case secondary
        case ghost
        case destructive
    }

    var variant: Variant = .primary

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .padding(.horizontal, 20)
            .background(background(isPressed: configuration.isPressed))
            .foregroundColor(foregroundColor)
            .overlay(borderOverlay)
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .opacity(configuration.isPressed ? 0.85 : 1)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.easeInOut(duration: 0.12), value: configuration.isPressed)
    }

    @ViewBuilder
    private func background(isPressed: Bool) -> some View {
        switch variant {
        case .primary:
            LinearGradient(
                colors: [SCPalette.accent, SCPalette.accentSoft],
                startPoint: .leading,
                endPoint: .trailing
            )
            .brightness(isPressed ? -0.05 : 0)
        case .secondary:
            SCPalette.secondary.opacity(isPressed ? 0.8 : 1)
        case .ghost:
            SCPalette.panelAlt.opacity(isPressed ? 0.7 : 0.5)
        case .destructive:
            SCPalette.error.opacity(isPressed ? 0.8 : 1)
        }
    }

    private var foregroundColor: Color {
        switch variant {
        case .primary:
            return .white
        case .secondary:
            return SCPalette.background
        case .ghost:
            return SCPalette.text
        case .destructive:
            return .white
        }
    }

    @ViewBuilder
    private var borderOverlay: some View {
        switch variant {
        case .ghost:
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(SCPalette.border, lineWidth: 1)
        case .primary, .secondary, .destructive:
            EmptyView()
        }
    }
}

// MARK: - Input Field

struct SCInputField: View {
    enum FieldKind {
        case text
        case secure
    }

    let label: String
    let placeholder: String
    @Binding var text: String
    var kind: FieldKind = .text
    var keyboard: UIKeyboardType = .default
    var textContentType: UITextContentType? = nil
    var autocapitalization: TextInputAutocapitalization = .never
    var error: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label.uppercased())
                .font(.caption)
                .foregroundColor(SCPalette.muted)
                .kerning(1.2)
            field
                .textInputAutocapitalization(autocapitalization)
                .keyboardType(keyboard)
                .textContentType(textContentType)
                .padding(.vertical, 14)
                .padding(.horizontal, 16)
                .background(SCPalette.panelAlt.opacity(0.65))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(borderColor, lineWidth: 1)
                )
                .cornerRadius(14)
                .foregroundColor(SCPalette.text)
            if let error {
                Text(error)
                    .font(.footnote)
                    .foregroundColor(SCPalette.error)
            }
        }
    }

    private var borderColor: Color {
        if error != nil { return SCPalette.error }
        return SCPalette.border
    }

    @ViewBuilder
    private var field: some View {
        switch kind {
        case .text:
            TextField(placeholder, text: $text)
        case .secure:
            SecureField(placeholder, text: $text)
        }
    }
}

// MARK: - Status Banner

struct SCStatusBanner: View {
    enum Variant {
        case info
        case success
        case warning
        case error
    }

    var message: String?
    var variant: Variant = .info

    private var palette: (color: Color, background: Color) {
        switch variant {
        case .info:
            return (SCPalette.secondary, SCPalette.secondary.opacity(0.12))
        case .success:
            return (SCPalette.success, SCPalette.success.opacity(0.15))
        case .warning:
            return (SCPalette.warning, SCPalette.warning.opacity(0.15))
        case .error:
            return (SCPalette.error, SCPalette.error.opacity(0.18))
        }
    }

    var body: some View {
        Group {
            if let message {
                HStack(alignment: .top, spacing: 12) {
                    Circle()
                        .fill(palette.color)
                        .frame(width: 10, height: 10)
                        .shadow(color: palette.color.opacity(0.6), radius: 6)
                        .padding(.top, 6)
                    Text(message)
                        .foregroundColor(SCPalette.text)
                        .font(.subheadline)
                    Spacer(minLength: 0)
                }
                .padding(.vertical, 12)
                .padding(.horizontal, 16)
                .background(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(palette.background)
                        .overlay(
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .stroke(palette.color.opacity(0.3), lineWidth: 1)
                        )
                )
            }
        }
    }
}

// MARK: - Spinner

struct SCSpinner: View {
    @State private var animate = false

    var body: some View {
        HStack(spacing: 8) {
            ForEach(0..<3, id: \.self) { index in
                Circle()
                    .fill(SCPalette.accent)
                    .frame(width: 10, height: 10)
                    .scaleEffect(animate ? 1 : 0.5)
                    .opacity(animate ? 1 : 0.3)
                    .animation(
                        Animation.easeInOut(duration: 0.7)
                            .repeatForever()
                            .delay(Double(index) * 0.15),
                        value: animate
                    )
            }
        }
        .onAppear { animate = true }
        .accessibilityLabel("Loading")
    }
}

// MARK: - Chip

struct SCChip: View {
    var label: String
    var isActive: Bool
    var color: Color = SCPalette.accent
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.subheadline)
                .fontWeight(isActive ? .semibold : .regular)
                .padding(.vertical, 8)
                .padding(.horizontal, 16)
                .background(
                    Capsule(style: .continuous)
                        .fill(isActive ? color.opacity(0.2) : Color.clear)
                )
                .overlay(
                    Capsule(style: .continuous)
                        .stroke(isActive ? color : SCPalette.border, lineWidth: 1)
                )
                .foregroundColor(isActive ? SCPalette.text : SCPalette.muted)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Countdown Ring

struct SCCountdownRing: View {
    var progress: Double // 0.0 to 1.0
    var lineWidth: CGFloat = 20
    var size: CGFloat = 200

    var body: some View {
        ZStack {
            Circle()
                .stroke(SCPalette.panelAlt, lineWidth: lineWidth)
            Circle()
                .trim(from: 0, to: progress)
                .stroke(
                    AngularGradient(
                        colors: [SCPalette.secondary, SCPalette.accent],
                        center: .center
                    ),
                    style: StrokeStyle(lineWidth: lineWidth, lineCap: .round)
                )
                .rotationEffect(.degrees(-90))
                .animation(.linear(duration: 1), value: progress)
            // Glow at the leading edge
            Circle()
                .trim(from: 0, to: progress)
                .stroke(
                    SCPalette.secondary.opacity(0.3),
                    style: StrokeStyle(lineWidth: lineWidth + 8, lineCap: .round)
                )
                .rotationEffect(.degrees(-90))
                .blur(radius: 4)
        }
        .frame(width: size, height: size)
    }
}

// MARK: - Neon Glow Modifier

struct NeonGlow: ViewModifier {
    var color: Color = SCPalette.accent
    var radius: CGFloat = 8

    func body(content: Content) -> some View {
        content
            .shadow(color: color.opacity(0.5), radius: radius)
            .shadow(color: color.opacity(0.2), radius: radius * 2)
    }
}

extension View {
    func neonGlow(color: Color = SCPalette.accent, radius: CGFloat = 8) -> some View {
        modifier(NeonGlow(color: color, radius: radius))
    }
}
