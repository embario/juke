import SwiftUI

/// The single content card every section is built on: `theme.card` fill,
/// 28pt corners, the prototype's soft drop shadow (and a hairline ring in dark mode).
struct JukeCard<Content: View>: View {
    @Environment(\.jukeTheme) private var theme
    var padding: EdgeInsets
    @ViewBuilder var content: Content

    init(padding: EdgeInsets = EdgeInsets(top: 22, leading: 32, bottom: 22, trailing: 32), @ViewBuilder content: () -> Content) {
        self.padding = padding
        self.content = content()
    }

    var body: some View {
        content
            .padding(padding)
            .background(theme.card.color, in: RoundedRectangle(cornerRadius: JukeRadius.card, style: .continuous))
            .overlay {
                if theme.shadow.ringOpacity > 0 {
                    RoundedRectangle(cornerRadius: JukeRadius.card, style: .continuous)
                        .strokeBorder(Color.white.opacity(theme.shadow.ringOpacity), lineWidth: 1)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: JukeRadius.card, style: .continuous))
            .shadow(color: theme.shadow.color, radius: theme.shadow.radius, y: theme.shadow.y)
    }
}

/// Fill for recessed areas inside a card.
struct JukeWell: ViewModifier {
    @Environment(\.jukeTheme) private var theme
    var cornerRadius: CGFloat = JukeRadius.well

    func body(content: Content) -> some View {
        content.background(theme.well.color, in: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
    }
}

extension View {
    func jukeWell(cornerRadius: CGFloat = JukeRadius.well) -> some View {
        modifier(JukeWell(cornerRadius: cornerRadius))
    }
}

/// Pill button in the accent colour (Play, Sign in, Start radio).
struct JukeAccentButtonStyle: ButtonStyle {
    @Environment(\.jukeTheme) private var theme
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(JukeFont.body(15, weight: .bold))
            .foregroundStyle(theme.onAccent.color)
            .padding(.horizontal, 20)
            .frame(minHeight: JukeMetrics.minimumHitTarget)
            .background(theme.accent.color.opacity(isEnabled ? 1 : 0.45), in: Capsule())
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .contentShape(Capsule())
    }
}

/// Pill button on the well colour (Open Radio, secondary actions).
struct JukeWellButtonStyle: ButtonStyle {
    @Environment(\.jukeTheme) private var theme

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(JukeFont.body(14, weight: .semibold))
            .foregroundStyle(theme.ink.color)
            .padding(.horizontal, 16)
            .frame(minHeight: JukeMetrics.minimumHitTarget)
            .background(theme.well.color, in: Capsule())
            .opacity(configuration.isPressed ? 0.8 : 1)
            .contentShape(Capsule())
    }
}

/// A small spinning record used by the mini player (and available to Radio).
struct VinylDisc: View {
    var label: Color
    var size: CGFloat = 40
    var isSpinning = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(paused: !isSpinning || reduceMotion)) { context in
            Canvas { canvas, area in
                let rect = CGRect(origin: .zero, size: area)
                canvas.fill(Path(ellipseIn: rect), with: .color(Color(red: 0.08, green: 0.08, blue: 0.08)))
                var radius = area.width / 2 - 2
                while radius > area.width * 0.22 {
                    let ring = rect.insetBy(dx: area.width / 2 - radius, dy: area.height / 2 - radius)
                    canvas.stroke(Path(ellipseIn: ring), with: .color(Color(red: 0.14, green: 0.14, blue: 0.14)), lineWidth: 1)
                    radius -= 4
                }
                let labelSide = area.width * 0.4
                let labelRect = CGRect(x: (area.width - labelSide) / 2, y: (area.height - labelSide) / 2, width: labelSide, height: labelSide)
                canvas.fill(Path(ellipseIn: labelRect), with: .color(label))
                // A small highlight so the rotation is visible.
                let highlight = CGRect(x: labelRect.midX - 1.5, y: labelRect.minY + 2, width: 3, height: 3)
                canvas.fill(Path(ellipseIn: highlight), with: .color(.white.opacity(0.55)))
            }
            .rotationEffect(.degrees(isSpinning && !reduceMotion ? (context.date.timeIntervalSinceReferenceDate * 200).truncatingRemainder(dividingBy: 360) : 0))
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}
