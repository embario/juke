import CoreGraphics
import Foundation

/// How records move in the crate. Mirrors the `crateFlipDirection` setting.
enum CrateMode: Sendable, Equatable {
    /// Coverflow: records stand side by side and turn towards the middle.
    case sideToSide
    /// A record bin: records stand one behind the other and the front one tips forward.
    case frontToBack

    init(_ direction: CrateFlipDirection) {
        self = direction == .frontToBack ? .frontToBack : .sideToSide
    }

    var direction: CrateFlipDirection { self == .frontToBack ? .frontToBack : .sideToSide }

    /// Drag distance (pt) that moves focus by one record.
    var dragUnit: CGFloat { self == .frontToBack ? 70 : 120 }
    /// Sleeve side length (pt).
    var sleeveSize: CGFloat { self == .frontToBack ? 200 : 210 }
    /// Distance from the top of the crate well to the sleeves' top edge.
    var sleeveTop: CGFloat { self == .frontToBack ? 46 : 22 }
    /// Width of the card holding the crate. The bin is narrower so there is no
    /// empty space on the sides (approved tweak to the prototype's 920 pt).
    var cardWidth: CGFloat { self == .frontToBack ? 680 : 920 }
    /// Width of the "Dig for anything" field.
    var searchWidth: CGFloat { self == .frontToBack ? 150 : 220 }
}

/// Where one sleeve sits relative to the crate's centre line, ported from the
/// prototype's `crateItems` transforms (`docs/design/juke-app/Round3.reference.html`).
///
/// SwiftUI order (inside out): scale, 3D rotation, offset, exactly like the CSS
/// `translate(…) rotate(…) scale(…)` string.
struct CrateSleeveTransform: Equatable, Sendable {
    var x: CGFloat = 0
    var y: CGFloat = 0
    /// Degrees around the horizontal axis (front-to-back: the front record tips forward).
    var rotationX: Double = 0
    /// Degrees around the vertical axis (side-to-side: side records turn inwards).
    var rotationY: Double = 0
    var scale: CGFloat = 1
    var opacity: Double = 1
    /// 1 is unchanged; lower values darken (CSS `brightness()`).
    var brightness: Double = 1
    var zIndex: Double = 0
}

enum CrateLayout {
    /// Height of the crate well.
    static let wellHeight: CGFloat = 256
    /// Milliseconds of release velocity added to a drag (momentum).
    static let momentumMilliseconds: CGFloat = 320
    /// A drag shorter than this is a click.
    static let dragThreshold: CGFloat = 4
    /// Scroll distance (pt) that moves focus by one record.
    static let wheelStep: CGFloat = 50
    /// Records drawn on each side of the focused one.
    static let visibleRadius = 7
    /// The prototype's 560 ms settle.
    static let settleDuration = 0.56

    /// Fractional focus while dragging: dragging towards the start (left or up)
    /// moves deeper into the crate.
    static func position(focus: Int, dragDelta: CGFloat, mode: CrateMode) -> CGFloat {
        CGFloat(focus) - dragDelta / mode.dragUnit
    }

    static func transform(index: Int, position: CGFloat, mode: CrateMode) -> CrateSleeveTransform {
        let offset = CGFloat(index) - position
        let distance = abs(offset)
        var result = CrateSleeveTransform()
        switch mode {
        case .frontToBack:
            if offset < 0 {
                // Already flipped past: tips forward and falls out of view.
                let fall = min(1, -offset)
                result.y = fall * 150
                result.rotationX = Double(-fall * 82)
                result.opacity = max(0, 1 - Double(fall) * 1.2)
                result.zIndex = 200
            } else {
                let depth = min(offset, 6)
                result.y = -depth * 20
                result.scale = 1 - depth * 0.045
                result.opacity = offset > 6 ? 0 : 1
                result.brightness = 1 - Double(depth) * 0.07
                result.zIndex = 100 - (Double(offset) * 10).rounded()
            }
        case .sideToSide:
            let sign: CGFloat = offset < 0 ? -1 : 1
            let turn = min(distance, 1)
            result.x = offset * 64 + sign * turn * 120
            result.rotationY = Double(-sign * turn * 60)
            result.scale = distance < 1 ? 1 - distance * 0.1 : 0.9 - min(distance - 1, 4) * 0.02
            result.opacity = distance > 5 ? 0 : 1
            result.brightness = 1 - Double(min(distance, 4)) * 0.06
            result.zIndex = 100 - (Double(distance) * 10).rounded()
        }
        return result
    }

    /// The record that ends up in front when a drag is released: distance plus
    /// `velocity` (pt per ms, along the drag axis) × 320 ms of momentum.
    static func releasedFocus(focus: Int, count: Int, dragDelta: CGFloat, velocity: CGFloat, mode: CrateMode) -> Int {
        let travel = dragDelta + velocity * momentumMilliseconds
        let steps = Int((-travel / mode.dragUnit).rounded())
        return clamp(focus + steps, count: count)
    }

    static func clamp(_ focus: Int, count: Int) -> Int {
        guard count > 0 else { return 0 }
        return min(count - 1, max(0, focus))
    }

    /// Indices worth drawing around the focus (the rest are fully transparent).
    static func visibleIndices(focus: Int, count: Int) -> Range<Int> {
        guard count > 0 else { return 0..<0 }
        let lower = max(0, focus - visibleRadius)
        let upper = min(count, focus + visibleRadius + 1)
        return lower..<max(lower, upper)
    }
}

/// Turns scroll-wheel and trackpad deltas into one-record steps.
///
/// Deltas use the web convention (positive = scrolling down/right = deeper
/// into the crate). Precise (trackpad) deltas accumulate until they pass
/// `CrateLayout.wheelStep`; each notch of a classic mouse wheel is one step.
struct CrateWheelAccumulator: Equatable, Sendable {
    private(set) var total: CGFloat = 0

    mutating func add(_ delta: CGFloat, precise: Bool = true) -> Int {
        guard delta != 0 else { return 0 }
        guard precise else {
            total = 0
            return delta > 0 ? 1 : -1
        }
        if (total > 0 && delta < 0) || (total < 0 && delta > 0) { total = 0 }
        total += delta
        guard abs(total) >= CrateLayout.wheelStep else { return 0 }
        let step = total > 0 ? 1 : -1
        total = 0
        return step
    }

    /// The delta along the crate's axis, from AppKit's scrolling deltas
    /// (which are inverted relative to the web convention).
    static func axisDelta(deltaX: CGFloat, deltaY: CGFloat, mode: CrateMode) -> CGFloat {
        switch mode {
        case .frontToBack: -deltaY
        case .sideToSide: abs(deltaX) > abs(deltaY) ? -deltaX : -deltaY
        }
    }
}
