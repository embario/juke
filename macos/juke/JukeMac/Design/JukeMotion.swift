import AppKit
import SwiftUI

/// Motion constants from the design reference. Every helper takes
/// `reduceMotion` (read `@Environment(\.accessibilityReduceMotion)`) and
/// returns `nil` when motion should be skipped, so it can be passed straight
/// to `withAnimation` or `.animation(_:value:)`.
enum JukeMotion {
    /// The prototype's signature easing, `cubic-bezier(.2,.8,.2,1)`.
    static func easeOutSoft(_ duration: Double) -> Animation {
        .timingCurve(0.2, 0.8, 0.2, 1, duration: duration)
    }

    /// `cubic-bezier(.4,0,1,1)`, used when a section leaves.
    static func easeInSharp(_ duration: Double) -> Animation {
        .timingCurve(0.4, 0, 1, 1, duration: duration)
    }

    static let navigationOutDuration = 0.2
    static let navigationInDuration = 0.48
    static let colorCrossfadeDuration = 0.9
    static let pageBackgroundDuration = 1.1
    static let controlDuration = 0.3

    /// Section leaving: opacity 1 → 0, y 0 → -8, scale 1 → 0.995 over 200 ms.
    static func navigationOut(reduceMotion: Bool) -> Animation? {
        reduceMotion ? nil : easeInSharp(navigationOutDuration)
    }

    /// Section entering: opacity 0 → 1, y 14 → 0, scale 0.985 → 1 over 480 ms.
    static func navigationIn(reduceMotion: Bool) -> Animation? {
        reduceMotion ? nil : easeOutSoft(navigationInDuration)
    }

    /// Card and well colours following new artwork (900 ms). Under Reduce
    /// Motion colours still change, with a short plain fade.
    static func colorCrossfade(reduceMotion: Bool) -> Animation {
        reduceMotion ? .linear(duration: 0.15) : .easeInOut(duration: colorCrossfadeDuration)
    }

    /// Selected-tab and small control transitions (300 ms).
    static func control(reduceMotion: Bool) -> Animation? {
        reduceMotion ? nil : .easeInOut(duration: controlDuration)
    }

    /// Stage offsets used by `SectionStage`.
    enum Stage {
        static let outOffset: CGFloat = -8
        static let outScale: CGFloat = 0.995
        static let inOffset: CGFloat = 14
        static let inScale: CGFloat = 0.985
    }

    /// The system Reduce Motion preference, for code outside a view.
    @MainActor
    static var systemPrefersReducedMotion: Bool {
        NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
    }
}
