import SwiftUI

/// Colour tokens for the Juke UI, computed from light/dark and an artwork
/// base colour exactly like the design reference's `palette(dark, base)`
/// (`docs/design/juke-app/Round3.reference.html`).
///
/// Read it in any view with `@Environment(\.jukeTheme) private var theme`
/// and use `theme.card.color`, `theme.ink.color`, etc. The root view injects
/// it and animates changes (track artwork, appearance) with
/// `JukeMotion.colorCrossfade`.
struct JukeTheme: Equatable, Sendable {
    struct Shadow: Equatable, Sendable {
        let color: Color
        let radius: CGFloat
        let y: CGFloat
        /// Hairline ring drawn around cards (dark mode's 1px white at 6%).
        let ringOpacity: Double
    }

    let isDark: Bool
    /// The artwork colour this palette was derived from.
    let base: RGB

    /// Window/page background.
    let bg: RGB
    /// The single content card.
    let card: RGB
    /// Recessed areas inside a card: segmented control track, dial, crate, progress track.
    let well: RGB
    /// Back face of a record sleeve.
    let sleeveBack: RGB
    /// Primary text and icons.
    let ink: RGB
    /// Secondary text.
    let sub: RGB
    /// Hairlines and outlines (ink at low opacity).
    let line: Color
    let lineOpacity: Double
    /// Dial ticks.
    let tick: Color
    let accent: RGB
    /// Text/icons on `accent`.
    let onAccent: RGB
    /// Selected chip fill.
    let accentSoft: RGB
    /// Photo-print paper in Memories.
    let print: RGB
    /// Card shadow.
    let shadow: Shadow
    /// Shadow for lifted items (dragged station, sleeve).
    let liftShadow: Shadow

    /// Used when nothing is playing or artwork tinting is off.
    static let neutralBase = RGB(hex: "#A39382")

    static func palette(dark: Bool, base: RGB) -> JukeTheme {
        if dark {
            let surface = RGB(hex: "#1B1A18")
            let ink = RGB(hex: "#F3EFE8")
            let accent = RGB(hex: "#FB7A3C")
            let text = [ink, RGB(hex: "#B8B1A7")]
            return JukeTheme(
                isDark: true, base: base,
                bg: tinted(RGB(hex: "#121110"), base, 0.08, text: text),
                card: tinted(surface, base, 0.18, text: text),
                well: tinted(surface, base, 0.28, text: text),
                sleeveBack: tinted(surface, base, 0.1, text: text),
                ink: ink,
                sub: RGB(hex: "#B8B1A7"),
                line: ink.color(opacity: 0.16), lineOpacity: 0.16,
                tick: ink.color(opacity: 0.32),
                accent: accent,
                onAccent: RGB(hex: "#1A0D05"),
                accentSoft: surface.mix(accent, 0.24),
                print: RGB(hex: "#E9E5DD"),
                shadow: Shadow(color: .black.opacity(0.55), radius: 35, y: 30, ringOpacity: 0.06),
                liftShadow: Shadow(color: .black.opacity(0.5), radius: 15, y: 14, ringOpacity: 0)
            )
        }
        let ink = RGB(hex: "#1C1A17")
        let accent = RGB(hex: "#C2410C")
        let text = [ink, RGB(hex: "#4E4943")]
        let warm = Color(.sRGB, red: 30 / 255, green: 20 / 255, blue: 10 / 255)
        return JukeTheme(
            isDark: false, base: base,
            bg: tinted(RGB(hex: "#EFECE6"), base, 0.07, text: text),
            card: tinted(RGB(hex: "#FFFFFF"), base, 0.15, text: text),
            well: tinted(RGB(hex: "#FFFFFF"), base, 0.27, text: text),
            sleeveBack: tinted(RGB(hex: "#FFFFFF"), base, 0.08, text: text),
            ink: ink,
            sub: RGB(hex: "#4E4943"),
            line: ink.color(opacity: 0.15), lineOpacity: 0.15,
            tick: ink.color(opacity: 0.3),
            accent: accent,
            onAccent: RGB(hex: "#FFFFFF"),
            accentSoft: RGB(hex: "#FFFFFF").mix(accent, 0.14),
            print: RGB(hex: "#FFFFFF"),
            shadow: Shadow(color: warm.opacity(0.12), radius: 35, y: 30, ringOpacity: 0),
            liftShadow: Shadow(color: warm.opacity(0.28), radius: 15, y: 14, ringOpacity: 0)
        )
    }

    /// Minimum contrast for `ink` and `sub` on every surface (WCAG AA body text).
    static let minimumTextContrast = 4.5

    /// `neutral.mix(base, amount)`, as in the reference, except that very light
    /// or very dark artwork gets a gentler tint where the full amount would
    /// drop `ink`/`sub` below WCAG AA. Typical artwork is unaffected.
    static func tinted(_ neutral: RGB, _ base: RGB, _ amount: Double, text: [RGB]) -> RGB {
        var t = amount
        while t > 0 {
            let surface = neutral.mix(base, t)
            if text.allSatisfy({ RGB.contrast($0, surface) >= minimumTextContrast }) { return surface }
            t -= 0.01
        }
        return neutral
    }

    /// Light-mode default for previews and the environment fallback.
    static let standard = JukeTheme.palette(dark: false, base: neutralBase)
}

extension EnvironmentValues {
    @Entry var jukeTheme: JukeTheme = .standard
}

/// Corner radii from the design reference.
enum JukeRadius {
    /// The single content card (28px).
    static let card: CGFloat = 28
    /// Wells: dial, crate, chat bubbles (16px).
    static let well: CGFloat = 16
    /// Station tiles and small panels (12px).
    static let tile: CGFloat = 12
    /// Record sleeves and artwork (6px).
    static let sleeve: CGFloat = 6
}

/// Spacing and sizes from the design reference.
enum JukeMetrics {
    static let headerHorizontalPadding: CGFloat = 40
    static let headerVerticalPadding: CGFloat = 20
    static let headerSideWidth: CGFloat = 220
    /// Minimum hit target for every control (44pt).
    static let minimumHitTarget: CGFloat = 44
    /// Stage bottom padding on Radio and on other sections (room for the mini pill).
    static let stageBottomPaddingRadio: CGFloat = 30
    static let stageBottomPaddingWithPill: CGFloat = 96
    static let miniPillBottomInset: CGFloat = 22
    static let radioCardWidth: CGFloat = 640
    static let memoriesCardWidth: CGFloat = 880
}

/// Typography. The design uses Bricolage Grotesque; it is not bundled yet, so
/// the app uses the system rounded design, which keeps the same friendly,
/// geometric feel. JetBrains Mono maps to the system monospaced design.
enum JukeFont {
    static func display(_ size: CGFloat, weight: Font.Weight = .semibold) -> Font {
        .system(size: size, weight: weight, design: .rounded)
    }

    static func body(_ size: CGFloat = 15, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .rounded)
    }

    static func mono(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .monospaced)
    }

    /// The "juke" wordmark (26px, bold, -0.5 tracking).
    static let wordmark = display(26, weight: .bold)
    /// Segmented nav labels (15px, semibold).
    static let navLabel = body(15, weight: .semibold)
}
