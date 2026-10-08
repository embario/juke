import CoreGraphics
import Testing
@testable import JukeApp

@Suite struct VinylSleeveTests {
    private let travel = VinylSleeve.travel(out: 130, side: 196)

    @Test func theRecordFollowsTheFingerWithinTheTravel() {
        #expect(VinylSleeve.offset(forTranslation: -40, putAway: false, travel: travel) == -40)
        #expect(VinylSleeve.offset(forTranslation: 30, putAway: true, travel: travel) == 30)
    }

    @Test func itResistsPastEitherEnd() {
        #expect(VinylSleeve.offset(forTranslation: -500, putAway: false, travel: travel) == -(travel + VinylSleeve.overshoot))
        #expect(VinylSleeve.offset(forTranslation: 500, putAway: false, travel: travel) == VinylSleeve.overshoot)
        #expect(VinylSleeve.offset(forTranslation: 500, putAway: true, travel: travel) == travel + VinylSleeve.overshoot)
    }

    @Test func aShortDragIsCancelled() {
        #expect(VinylSleeve.outcome(translation: -travel * 0.3, predicted: -travel * 0.4, putAway: false, travel: travel) == .none)
        #expect(VinylSleeve.outcome(translation: travel * 0.3, predicted: travel * 0.4, putAway: true, travel: travel) == .none)
    }

    @Test func pastHalfwayOrAFlingCommits() {
        #expect(VinylSleeve.outcome(translation: -travel * 0.6, predicted: -travel * 0.6, putAway: false, travel: travel) == .putAway)
        #expect(VinylSleeve.outcome(translation: -10, predicted: -travel, putAway: false, travel: travel) == .putAway)
        #expect(VinylSleeve.outcome(translation: travel * 0.6, predicted: 0, putAway: true, travel: travel) == .resume)
    }

    @Test func draggingTheWrongWayNeverCommits() {
        #expect(VinylSleeve.outcome(translation: travel, predicted: travel * 2, putAway: false, travel: travel) == .none)
        #expect(VinylSleeve.outcome(translation: -travel, predicted: -travel * 2, putAway: true, travel: travel) == .none)
    }
}
