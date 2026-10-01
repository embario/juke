import CoreGraphics
import Foundation

/// Pure gesture and layout math for the Radio card, taken from the design
/// reference (`docs/design/juke-app/Round3.reference.html`: `vinylDown`,
/// `dialDown`, `enterHold`, `placeHold`, `commitHold`, `tuneNearest`,
/// `press`). Kept free of SwiftUI so it is unit tested directly.
enum RadioGesture {
    /// Press-and-hold threshold for the dial, the `+` reaction and Skip (450 ms).
    static let holdDelay: Duration = .milliseconds(450)
    /// A release more than this long after the last move carries no fling.
    static let flingWindow: TimeInterval = 0.09

    /// Exponentially smoothed pointer velocity, as in the reference
    /// (`v = w * (Δ / Δt) + (1 - w) * v`). `dt` is in milliseconds.
    static func smoothedVelocity(previous: Double, delta: Double, dtMilliseconds: Double, weight: Double) -> Double {
        weight * (delta / max(1, dtMilliseconds)) + (1 - weight) * previous
    }

    /// Velocity to use for a fling at release, or 0 when the pointer rested.
    static func releaseVelocity(_ velocity: Double, sinceLastMove: TimeInterval) -> Double {
        sinceLastMove > flingWindow ? 0 : velocity
    }

    /// "1:05"
    static func clock(_ seconds: TimeInterval) -> String {
        let value = max(0, Int(seconds.isFinite ? seconds.rounded() : 0))
        return "\(value / 60):" + String(format: "%02d", value % 60)
    }
}

/// Spinning the record's outer ring seeks: one full turn is 14 seconds.
enum VinylSeek {
    static let secondsPerTurn: TimeInterval = 14
    /// Grabs inside this fraction of the radius move the label instead of seeking.
    static let labelRadiusFraction: CGFloat = 0.42
    /// Degrees of rotation before a press counts as a spin rather than a click.
    static let spinThresholdDegrees: Double = 3
    /// Fling multiplier: degrees per (degree/ms) of release velocity.
    static let flingFactor: Double = 380
    /// The idle spin: one turn every 5.2 s while playing.
    static let idleTurnDuration: TimeInterval = 5.2

    /// Whether a press at `point` in a disc of `size` grabs the centre label.
    static func isLabelGrab(_ point: CGPoint, in size: CGSize) -> Bool {
        let radius = min(size.width, size.height) / 2
        guard radius > 0 else { return false }
        let distance = hypot(point.x - size.width / 2, point.y - size.height / 2)
        return distance / radius < labelRadiusFraction
    }

    /// Angle of `point` around the disc's centre, in radians.
    static func angle(of point: CGPoint, in size: CGSize) -> Double {
        atan2(Double(point.y - size.height / 2), Double(point.x - size.width / 2))
    }

    /// The signed change between two angles, wrapped to (-π, π].
    static func wrappedDelta(from previous: Double, to current: Double) -> Double {
        var delta = current - previous
        if delta > .pi { delta -= 2 * .pi }
        if delta < -.pi { delta += 2 * .pi }
        return delta
    }

    /// Seconds of seek for a rotation in degrees (clockwise is forward).
    static func seconds(forDegrees degrees: Double) -> TimeInterval {
        degrees / 360 * secondsPerTurn
    }

    static func degrees(forSeconds seconds: TimeInterval) -> Double {
        seconds / secondsPerTurn * 360
    }

    /// Total rotation at release, including fling momentum.
    static func releaseDegrees(dragDegrees: Double, velocity degreesPerMillisecond: Double, sinceLastMove: TimeInterval) -> Double {
        dragDegrees + RadioGesture.releaseVelocity(degreesPerMillisecond, sinceLastMove: sinceLastMove) * flingFactor
    }

    enum Outcome: Equatable {
        /// Seek to this position.
        case seek(TimeInterval)
        /// Spun past the end: move on to the next song.
        case advance
    }

    /// Where a spin from `position` lands in a track of `duration`.
    static func outcome(position: TimeInterval, duration: TimeInterval, degrees: Double) -> Outcome {
        let target = position + seconds(forDegrees: degrees)
        if duration > 0, target >= duration - 1 { return .advance }
        return .seek(max(0, target))
    }

    /// The seek preview target, clamped to the track.
    static func previewTarget(position: TimeInterval, duration: TimeInterval, delta: TimeInterval) -> TimeInterval {
        max(0, min(max(duration, 0), position + delta))
    }

    /// "+0:22 → 1:52" (or "−0:10 → 1:20").
    static func bubbleText(delta: TimeInterval, target: TimeInterval) -> String {
        (delta >= 0 ? "+" : "−") + RadioGesture.clock(abs(delta)) + " → " + RadioGesture.clock(target)
    }
}

/// Sliding the centre label into or out of the sleeve.
enum VinylLabelSlide {
    static let moveThreshold: CGFloat = 4
    static let putAwayDistance: CGFloat = -80
    static let resumeDistance: CGFloat = 70

    static func clamped(_ dx: CGFloat, putAway: Bool) -> CGFloat {
        max(-190, min(putAway ? 190 : 40, dx))
    }

    enum Outcome: Equatable { case none, putAway, resume }

    static func outcome(dx: CGFloat, putAway: Bool) -> Outcome {
        if !putAway, dx < putAwayDistance { return .putAway }
        if putAway, dx > resumeDistance { return .resume }
        return .none
    }
}

/// The FM dial: an 88–108 MHz band, 56 points per MHz, with a "+ New" slot
/// past the top of the band.
enum FMDial {
    static let pointsPerMHz: CGFloat = 56
    static let bandStart: Double = 88
    static let lowest: Double = 88.1
    static let highest: Double = 107.9
    /// Where the "+ New" slot sits (past 107.9).
    static let newSlot: Double = 109.6
    /// Stations closer than this are moved apart (the server applies the same rule).
    static let minimumSpacing: Double = 2.2
    static let bandWidth: CGFloat = x(for: 111)
    static let itemWidth: CGFloat = 124
    /// Drag distance before a press becomes a drag.
    static let dragThreshold: CGFloat = 5
    /// Fling multiplier: points per (point/ms) of release velocity.
    static let flingFactor: Double = 420
    /// Hold-to-move auto-scroll: edge zone and speed (MHz per frame).
    static let edgeZone: CGFloat = 48
    static let edgeStep: Double = 0.07
    /// Rubber-band factor past the ends.
    static let rubberBand: CGFloat = 0.35
    /// Wheel/trackpad distance per station step.
    static let wheelStep: CGFloat = 60

    /// Position of a frequency on the band, in points from 88.0.
    static func x(for frequency: Double) -> CGFloat {
        CGFloat(frequency - bandStart) * pointsPerMHz
    }

    static func frequency(atX x: CGFloat) -> Double {
        bandStart + Double(x / pointsPerMHz)
    }

    /// Nearest odd tenth in 88.1…107.9, as the reference's `snapFreq`.
    static func snap(_ frequency: Double) -> Double {
        let steps = ((frequency - 0.1) / 0.2).rounded()
        return tenths(max(lowest, min(highest, steps * 0.2 + 0.1)))
    }

    static func tenths(_ value: Double) -> Double { (value * 10).rounded() / 10 }

    /// The band's horizontal offset so `center` sits under the needle,
    /// plus a live drag, rubber-banded past the ends.
    static func bandOffset(center: Double, dragDelta: CGFloat) -> CGFloat {
        var offset = -x(for: center) + dragDelta
        let maxOffset = -x(for: lowest)
        let minOffset = -x(for: newSlot)
        if offset > maxOffset { offset = maxOffset + (offset - maxOffset) * rubberBand }
        if offset < minOffset { offset = minOffset + (offset - minOffset) * rubberBand }
        return offset
    }

    /// The frequency the dial settles on after a drag of `dx` points
    /// released at `velocity` points/ms.
    static func releaseCenter(tuned: Double, dragDelta: CGFloat, velocity: Double, sinceLastMove: TimeInterval) -> Double {
        let fling = RadioGesture.releaseVelocity(velocity, sinceLastMove: sinceLastMove) * flingFactor
        return tuned - (Double(dragDelta) + fling) / Double(pointsPerMHz)
    }

    enum Mark: Hashable, Sendable {
        case station(Radio.ID)
        case newStation
    }

    struct Slot: Hashable, Sendable {
        let mark: Mark
        let frequency: Double
    }

    static func slots(_ stations: [Radio.Station]) -> [Slot] {
        (stations.map { Slot(mark: .station($0.id), frequency: $0.frequency) } + [Slot(mark: .newStation, frequency: newSlot)])
            .sorted { $0.frequency < $1.frequency }
    }

    /// The slot nearest `center` (ties keep the lower frequency).
    static func nearest(to center: Double, in slots: [Slot]) -> Slot? {
        slots.min { abs($0.frequency - center) < abs($1.frequency - center) }
    }

    /// The neighbouring slot one step up (`direction` 1) or down (-1) from `tuned`.
    static func step(from tuned: Double, direction: Int, in slots: [Slot]) -> Slot? {
        guard !slots.isEmpty else { return nil }
        let index = slots.firstIndex { abs($0.frequency - tuned) < 0.01 }
            ?? slots.firstIndex { $0.frequency > tuned }.map { direction > 0 ? $0 - 1 : $0 }
            ?? slots.count - 1
        let target = max(0, min(slots.count - 1, index + direction))
        return slots[target]
    }

    /// Settle animation length for a move of `distance` MHz (ms → s).
    static func tuneDuration(distance: Double) -> TimeInterval {
        min(1500, 340 + 60 * distance) / 1000
    }

    // MARK: Hold to move

    /// Offset between the pointer and the held station, in MHz, so the
    /// station does not jump under the finger.
    static func holdGrab(pointerFromCenter: CGFloat, stationFrequency: Double, view: Double) -> Double {
        Double(pointerFromCenter / pointsPerMHz) - (stationFrequency - view)
    }

    /// The snapped frequency under the pointer while holding.
    static func holdFrequency(view: Double, pointerFromCenter: CGFloat, grab: Double) -> Double {
        snap(view + Double(pointerFromCenter / pointsPerMHz) - grab)
    }

    /// -1 / 0 / 1 when the pointer is in the left / middle / right edge zone.
    static func edgeDirection(pointerX: CGFloat, width: CGFloat) -> Int {
        if pointerX < edgeZone { return -1 }
        if pointerX > width - edgeZone { return 1 }
        return 0
    }

    /// One auto-scroll frame while holding at an edge.
    static func scrolledView(_ view: Double, direction: Int) -> Double {
        max(lowest, min(highest, view + Double(direction) * edgeStep))
    }

    /// The nearest frequency at least `minimumSpacing` from every other
    /// station, searching outward from `frequency` (the reference's
    /// `commitHold`). The server makes the final decision.
    static func freeSlot(near frequency: Double, others: [Double]) -> Double {
        func isFree(_ value: Double) -> Bool { others.allSatisfy { abs($0 - value) >= minimumSpacing - 0.001 } }
        let start = snap(frequency)
        if isFree(start) { return start }
        for k in 0..<100 {
            let offset = Double((k + 2) / 2) * 0.2 * (k % 2 == 1 ? -1 : 1)
            let candidate = snap(start + offset)
            if isFree(candidate) { return candidate }
        }
        return start
    }
}
