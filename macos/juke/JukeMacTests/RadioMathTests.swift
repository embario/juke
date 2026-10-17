import CoreGraphics
import XCTest
@testable import Juke

final class VinylSeekTests: XCTestCase {
    func testOneTurnIsFourteenSeconds() {
        XCTAssertEqual(VinylSeek.seconds(forDegrees: 360), 14, accuracy: 0.0001)
        XCTAssertEqual(VinylSeek.seconds(forDegrees: -180), -7, accuracy: 0.0001)
        XCTAssertEqual(VinylSeek.degrees(forSeconds: 15), 360 * 15 / 14, accuracy: 0.0001)
    }

    func testAngleDeltaWrapsAcrossPi() {
        XCTAssertEqual(VinylSeek.wrappedDelta(from: 3.0, to: -3.0), 2 * .pi - 6, accuracy: 0.0001)
        XCTAssertEqual(VinylSeek.wrappedDelta(from: -3.0, to: 3.0), 6 - 2 * .pi, accuracy: 0.0001)
        XCTAssertEqual(VinylSeek.wrappedDelta(from: 0.1, to: 0.4), 0.3, accuracy: 0.0001)
    }

    func testAngleIsMeasuredAroundTheCentre() {
        let size = CGSize(width: 184, height: 184)
        XCTAssertEqual(VinylSeek.angle(of: CGPoint(x: 184, y: 92), in: size), 0, accuracy: 0.0001)
        XCTAssertEqual(VinylSeek.angle(of: CGPoint(x: 92, y: 184), in: size), .pi / 2, accuracy: 0.0001)
    }

    func testLabelGrabIsTheInnerFortyTwoPercent() {
        let size = CGSize(width: 184, height: 184)
        XCTAssertTrue(VinylSeek.isLabelGrab(CGPoint(x: 92, y: 92), in: size))
        XCTAssertTrue(VinylSeek.isLabelGrab(CGPoint(x: 92 + 38, y: 92), in: size))
        XCTAssertFalse(VinylSeek.isLabelGrab(CGPoint(x: 92 + 40, y: 92), in: size))
        XCTAssertFalse(VinylSeek.isLabelGrab(CGPoint(x: 180, y: 92), in: size))
    }

    func testFlingAddsMomentumOnlyForAQuickRelease() {
        XCTAssertEqual(VinylSeek.releaseDegrees(dragDegrees: 90, velocity: 0.5, sinceLastMove: 0.02), 90 + 190, accuracy: 0.0001)
        XCTAssertEqual(VinylSeek.releaseDegrees(dragDegrees: 90, velocity: 0.5, sinceLastMove: 0.2), 90, accuracy: 0.0001)
    }

    func testOutcomeSeeksOrAdvances() {
        XCTAssertEqual(VinylSeek.outcome(position: 60, duration: 200, degrees: 360), .seek(74))
        XCTAssertEqual(VinylSeek.outcome(position: 5, duration: 200, degrees: -360), .seek(0))
        XCTAssertEqual(VinylSeek.outcome(position: 190, duration: 200, degrees: 360), .advance)
    }

    func testBubbleText() {
        XCTAssertEqual(VinylSeek.bubbleText(delta: 22, target: 112), "+0:22 → 1:52")
        XCTAssertEqual(VinylSeek.bubbleText(delta: -10, target: 80), "−0:10 → 1:20")
        XCTAssertEqual(VinylSeek.previewTarget(position: 190, duration: 200, delta: 30), 200)
    }

    func testSmoothedVelocity() {
        XCTAssertEqual(RadioGesture.smoothedVelocity(previous: 0, delta: 10, dtMilliseconds: 10, weight: 0.75), 0.75, accuracy: 0.0001)
        XCTAssertEqual(RadioGesture.smoothedVelocity(previous: 1, delta: 10, dtMilliseconds: 0, weight: 0.75), 7.75, accuracy: 0.0001,
                       "dt is at least 1 ms")
    }

    func testLabelSlide() {
        XCTAssertEqual(VinylLabelSlide.clamped(80, putAway: false), 40)
        XCTAssertEqual(VinylLabelSlide.clamped(-300, putAway: false), -190)
        XCTAssertEqual(VinylLabelSlide.clamped(300, putAway: true), 190)
        XCTAssertEqual(VinylLabelSlide.outcome(dx: -81, putAway: false), .putAway)
        XCTAssertEqual(VinylLabelSlide.outcome(dx: -60, putAway: false), VinylLabelSlide.Outcome.none)
        XCTAssertEqual(VinylLabelSlide.outcome(dx: 71, putAway: true), .resume)
        XCTAssertEqual(VinylLabelSlide.outcome(dx: 71, putAway: false), VinylLabelSlide.Outcome.none)
    }

    func testClock() {
        XCTAssertEqual(RadioGesture.clock(0), "0:00")
        XCTAssertEqual(RadioGesture.clock(65.4), "1:05")
        XCTAssertEqual(RadioGesture.clock(-3), "0:00")
        XCTAssertEqual(RadioGesture.clock(.nan), "0:00")
    }
}

final class FMDialMathTests: XCTestCase {
    private func station(_ id: String, _ frequency: Double) -> Radio.Station {
        Radio.Station(id: Radio.ID(id), name: id, kind: .custom, frequency: frequency, seeds: [], thumbnails: [], feelings: [],
                      learning: true, exclusions: [], createdAt: Date(timeIntervalSince1970: 0))
    }

    func testFrequencyAndPositionRoundTrip() {
        XCTAssertEqual(FMDial.x(for: 88), 0)
        XCTAssertEqual(FMDial.x(for: 90), 112)
        XCTAssertEqual(FMDial.frequency(atX: FMDial.x(for: 97.1)), 97.1, accuracy: 0.0001)
        XCTAssertEqual(FMDial.bandWidth, 23 * 56)
    }

    func testSnapToOddTenthsInBand() {
        XCTAssertEqual(FMDial.snap(92.3), 92.3)
        XCTAssertEqual(FMDial.snap(92.24), 92.3)
        XCTAssertEqual(FMDial.snap(92.18), 92.1)
        XCTAssertEqual(FMDial.snap(80), 88.1)
        XCTAssertEqual(FMDial.snap(120), 107.9)
    }

    func testBandOffsetRubberBandsPastTheEnds() {
        XCTAssertEqual(FMDial.bandOffset(center: 97.1, dragDelta: 0), -FMDial.x(for: 97.1), accuracy: 0.001)
        let maxOffset = -FMDial.x(for: 88.1)
        XCTAssertEqual(FMDial.bandOffset(center: 88.1, dragDelta: 100), maxOffset + 35, accuracy: 0.001)
        let minOffset = -FMDial.x(for: FMDial.newSlot)
        XCTAssertEqual(FMDial.bandOffset(center: FMDial.newSlot, dragDelta: -100), minOffset - 35, accuracy: 0.001)
    }

    func testReleaseCenterIncludesFling() {
        XCTAssertEqual(FMDial.releaseCenter(tuned: 92.3, dragDelta: -112, velocity: 0, sinceLastMove: 0), 94.3, accuracy: 0.0001)
        // -1 pt/ms flick adds 420 pt (7.5 MHz).
        XCTAssertEqual(FMDial.releaseCenter(tuned: 92.3, dragDelta: 0, velocity: -1, sinceLastMove: 0.01), 92.3 + 7.5, accuracy: 0.0001)
        XCTAssertEqual(FMDial.releaseCenter(tuned: 92.3, dragDelta: 0, velocity: -1, sinceLastMove: 0.5), 92.3, accuracy: 0.0001)
    }

    func testNearestAndStepIncludeNewStationSlot() {
        let slots = FMDial.slots([station("b", 97.1), station("a", 88.7), station("c", 105.9)])
        XCTAssertEqual(slots.map(\.frequency), [88.7, 97.1, 105.9, FMDial.newSlot])
        XCTAssertEqual(FMDial.nearest(to: 95, in: slots)?.mark, .station("b"))
        XCTAssertEqual(FMDial.nearest(to: 120, in: slots)?.mark, .newStation, "a hard flick past the end lands on + New")
        XCTAssertEqual(FMDial.step(from: 97.1, direction: 1, in: slots)?.mark, .station("c"))
        XCTAssertEqual(FMDial.step(from: 97.1, direction: -1, in: slots)?.mark, .station("a"))
        XCTAssertEqual(FMDial.step(from: 88.7, direction: -1, in: slots)?.mark, .station("a"))
        XCTAssertEqual(FMDial.step(from: 105.9, direction: 1, in: slots)?.mark, .newStation)
        XCTAssertEqual(FMDial.step(from: 92, direction: 1, in: slots)?.mark, .station("b"))
    }

    func testTuneDuration() {
        XCTAssertEqual(FMDial.tuneDuration(distance: 0), 0.34, accuracy: 0.0001)
        XCTAssertEqual(FMDial.tuneDuration(distance: 5), 0.64, accuracy: 0.0001)
        XCTAssertEqual(FMDial.tuneDuration(distance: 100), 1.5, accuracy: 0.0001)
    }

    func testHoldKeepsTheGrabOffsetAndSnaps() {
        // Grab a station at 97.1 while the dial is centred on 92.3, 20 pt right of its centre.
        let pointer = FMDial.x(for: 97.1) - FMDial.x(for: 92.3) + 20
        let grab = FMDial.holdGrab(pointerFromCenter: pointer, stationFrequency: 97.1, view: 92.3)
        XCTAssertEqual(FMDial.holdFrequency(view: 92.3, pointerFromCenter: pointer, grab: grab), 97.1)
        // Drag it 112 pt (2 MHz) right.
        XCTAssertEqual(FMDial.holdFrequency(view: 92.3, pointerFromCenter: pointer + 112, grab: grab), 99.1)
        XCTAssertEqual(FMDial.holdFrequency(view: 92.3, pointerFromCenter: pointer + 2000, grab: grab), 107.9)
    }

    func testEdgeAutoScroll() {
        XCTAssertEqual(FMDial.edgeDirection(pointerX: 10, width: 480), -1)
        XCTAssertEqual(FMDial.edgeDirection(pointerX: 240, width: 480), 0)
        XCTAssertEqual(FMDial.edgeDirection(pointerX: 470, width: 480), 1)
        XCTAssertEqual(FMDial.scrolledView(92.3, direction: 1), 92.37, accuracy: 0.0001)
        XCTAssertEqual(FMDial.scrolledView(88.12, direction: -1), 88.1, accuracy: 0.0001)
    }

    func testHoldCommitFindsAFreeSlot() {
        XCTAssertEqual(FMDial.freeSlot(near: 95.3, others: [88.7, 105.9]), 95.3)
        XCTAssertEqual(FMDial.freeSlot(near: 97.5, others: [97.1]), 99.3, "searches up first, then down")
        XCTAssertEqual(FMDial.freeSlot(near: 96.9, others: [97.1]), 94.9)
        XCTAssertEqual(FMDial.freeSlot(near: 89.1, others: [88.7]), 90.9)
        XCTAssertEqual(FMDial.freeSlot(near: 96.9, others: [97.1], preferring: -1), 94.9)
        XCTAssertEqual(FMDial.freeSlot(near: 97.5, others: [97.1], preferring: -1), 94.9, "moving down never jumps up past a neighbour")
    }
}
