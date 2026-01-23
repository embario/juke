import SwiftUI
import UIKit

// MARK: - Color Palette

enum TuneTriviaPalette {
    // Backgrounds
    static let background = Color(hex: "#faf8f5")      // Cream White
    static let panel = Color(hex: "#fff5eb")           // Soft Peach
    static let panelAlt = Color(hex: "#ffffff")        // Pure White

    // Primary Colors
    static let accent = Color(hex: "#ff6b6b")          // Coral Pop
    static let accentSoft = Color(hex: "#ff8e8e")      // Light Coral

    // Secondary Colors
    static let secondary = Color(hex: "#4ecdc4")       // Ocean Teal
    static let tertiary = Color(hex: "#9b5de5")        // Grape Purple
    static let highlight = Color(hex: "#ffe66d")       // Sunny Yellow

    // Text Colors
    static let text = Color(hex: "#2d3436")            // Charcoal
    static let muted = Color(hex: "#636e72")           // Slate Gray

    // Status Colors
    static let success = Color(hex: "#4ecdc4")         // Teal (same as secondary)
    static let warning = Color(hex: "#ffe66d")         // Yellow
    static let error = Color(hex: "#ff6b6b")           // Coral (same as accent)

    // Borders
    static let border = Color.black.opacity(0.06)
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

struct TuneTriviaBackground: View {
    var body: some View {
        TuneTriviaPalette.background
            .ignoresSafeArea()
    }
}

// MARK: - Card

struct TuneTriviaCard<Content: View>: View {
    private let padding: CGFloat
    private let accentColor: Color?
    private let content: Content

    init(padding: CGFloat = 20, accentColor: Color? = nil, @ViewBuilder content: () -> Content) {
        self.padding = padding
        self.accentColor = accentColor
        self.content = content()
    }

    var body: some View {
        VStack(spacing: 0) {
            if let accentColor {
                accentColor
                    .frame(height: 6)
                    .clipShape(
                        .rect(topLeadingRadius: 20, topTrailingRadius: 20)
                    )
            }
            content
                .padding(padding)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(TuneTriviaPalette.panel)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .shadow(color: .black.opacity(0.06), radius: 12, x: 0, y: 4)
    }
}

// MARK: - Button Styles

struct TuneTriviaButtonStyle: ButtonStyle {
    enum Variant {
        case primary
        case secondary
        case ghost
        case link
    }

    var variant: Variant = .primary
    var isFullWidth: Bool = true

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .frame(maxWidth: isFullWidth ? .infinity : nil)
            .padding(.vertical, 16)
            .padding(.horizontal, 24)
            .background(background(isPressed: configuration.isPressed))
            .foregroundColor(foregroundColor)
            .overlay(borderOverlay)
            .clipShape(Capsule(style: .continuous))
            .shadow(color: shadowColor(isPressed: configuration.isPressed), radius: configuration.isPressed ? 4 : 8, x: 0, y: configuration.isPressed ? 2 : 4)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.easeInOut(duration: 0.15), value: configuration.isPressed)
    }

    @ViewBuilder
    private func background(isPressed: Bool) -> some View {
        switch variant {
        case .primary:
            TuneTriviaPalette.accent
                .brightness(isPressed ? -0.05 : 0)
        case .secondary:
            TuneTriviaPalette.secondary
                .brightness(isPressed ? -0.05 : 0)
        case .ghost:
            TuneTriviaPalette.panel
                .opacity(isPressed ? 0.8 : 1)
        case .link:
            Color.clear
        }
    }

    private var foregroundColor: Color {
        switch variant {
        case .primary, .secondary:
            return .white
        case .ghost:
            return TuneTriviaPalette.text
        case .link:
            return TuneTriviaPalette.secondary
        }
    }

    @ViewBuilder
    private var borderOverlay: some View {
        switch variant {
        case .ghost:
            Capsule(style: .continuous)
                .stroke(TuneTriviaPalette.border, lineWidth: 1)
        case .primary, .secondary, .link:
            EmptyView()
        }
    }

    private func shadowColor(isPressed: Bool) -> Color {
        switch variant {
        case .primary:
            return TuneTriviaPalette.accent.opacity(isPressed ? 0.15 : 0.3)
        case .secondary:
            return TuneTriviaPalette.secondary.opacity(isPressed ? 0.15 : 0.3)
        case .ghost, .link:
            return .clear
        }
    }
}

// MARK: - Input Field

struct TuneTriviaInputField: View {
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
        VStack(alignment: .leading, spacing: 8) {
            Text(label)
                .font(.subheadline)
                .foregroundColor(TuneTriviaPalette.muted)
            field
                .textInputAutocapitalization(autocapitalization)
                .keyboardType(keyboard)
                .textContentType(textContentType)
                .padding(.vertical, 14)
                .padding(.horizontal, 16)
                .background(TuneTriviaPalette.panel)
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(error == nil ? TuneTriviaPalette.border : TuneTriviaPalette.error, lineWidth: error == nil ? 1 : 2)
                )
                .cornerRadius(16)
                .foregroundColor(TuneTriviaPalette.text)
            if let error {
                Text(error)
                    .font(.footnote)
                    .foregroundColor(TuneTriviaPalette.error)
            }
        }
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

struct TuneTriviaStatusBanner: View {
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
            return (TuneTriviaPalette.secondary, TuneTriviaPalette.secondary.opacity(0.15))
        case .success:
            return (TuneTriviaPalette.success, TuneTriviaPalette.success.opacity(0.15))
        case .warning:
            return (TuneTriviaPalette.warning, TuneTriviaPalette.warning.opacity(0.2))
        case .error:
            return (TuneTriviaPalette.error, TuneTriviaPalette.error.opacity(0.15))
        }
    }

    var body: some View {
        Group {
            if let message {
                HStack(alignment: .top, spacing: 12) {
                    Circle()
                        .fill(palette.color)
                        .frame(width: 10, height: 10)
                        .padding(.top, 5)
                    Text(message)
                        .foregroundColor(TuneTriviaPalette.text)
                        .font(.subheadline)
                    Spacer(minLength: 0)
                }
                .padding(.vertical, 14)
                .padding(.horizontal, 16)
                .background(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(palette.background)
                )
            }
        }
    }
}

// MARK: - Spinner

struct TuneTriviaSpinner: View {
    @State private var animate = false

    var body: some View {
        HStack(spacing: 6) {
            ForEach(0..<3) { index in
                Circle()
                    .fill(TuneTriviaPalette.accent)
                    .frame(width: 10, height: 10)
                    .scaleEffect(animate ? 1 : 0.5)
                    .animation(
                        Animation.easeInOut(duration: 0.6)
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

// MARK: - Chip / Tag

struct TuneTriviaChip: View {
    var label: String
    var color: Color = TuneTriviaPalette.secondary
    var isActive: Bool = true

    var body: some View {
        Text(label)
            .font(.caption)
            .fontWeight(.medium)
            .padding(.vertical, 6)
            .padding(.horizontal, 12)
            .background(
                Capsule(style: .continuous)
                    .fill(color.opacity(isActive ? 0.2 : 0.1))
            )
            .foregroundColor(isActive ? color : TuneTriviaPalette.muted)
    }
}

// MARK: - Score Badge

struct TuneTriviaScoreBadge: View {
    var rank: Int
    var isHighlighted: Bool = false

    private var backgroundColor: Color {
        switch rank {
        case 1:
            return TuneTriviaPalette.highlight
        case 2, 3:
            return TuneTriviaPalette.muted.opacity(0.2)
        default:
            return TuneTriviaPalette.muted.opacity(0.15)
        }
    }

    var body: some View {
        Text("\(rank)")
            .font(.subheadline)
            .fontWeight(.bold)
            .frame(width: 36, height: 36)
            .background(
                Circle()
                    .fill(isHighlighted ? TuneTriviaPalette.accent.opacity(0.2) : backgroundColor)
            )
            .foregroundColor(isHighlighted ? TuneTriviaPalette.accent : TuneTriviaPalette.text)
    }
}

// MARK: - Progress Ring

struct TuneTriviaProgressRing: View {
    var progress: Double // 0.0 to 1.0
    var lineWidth: CGFloat = 8
    var size: CGFloat = 200

    var body: some View {
        ZStack {
            Circle()
                .stroke(TuneTriviaPalette.panel, lineWidth: lineWidth)
            Circle()
                .trim(from: 0, to: progress)
                .stroke(
                    TuneTriviaPalette.secondary,
                    style: StrokeStyle(lineWidth: lineWidth, lineCap: .round)
                )
                .rotationEffect(.degrees(-90))
                .animation(.easeInOut(duration: 0.3), value: progress)
        }
        .frame(width: size, height: size)
    }
}
