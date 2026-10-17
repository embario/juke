import CoreGraphics
import Testing
@testable import JukeApp

@Suite struct ControlsCenteringTests {
    @Test func theControlsAreAlwaysInTheMiddle() {
        for width in [320, 375, 390, 402, 430] as [CGFloat] {
            let x = ControlsCentering.centerX(container: width, center: 108)
            #expect(abs((x + 54) - width / 2) <= 0.5, "width \(width)")
        }
    }

    @Test func sidesShareWhatTheControlsLeaveOver() {
        let side = ControlsCentering.sideWidth(container: 350, center: 108, gap: 8)
        #expect(side == 113)
        // Left and right get the same room, so a wide left side can never move the middle.
        #expect(ControlsCentering.sideWidth(container: 350, center: 108, gap: 8) * 2 + 2 * 8 + 108 == 350)
    }

    @Test func controlsWiderThanTheRowLeaveNoRoomForTheSides() {
        #expect(ControlsCentering.sideWidth(container: 100, center: 108, gap: 8) == 0)
    }

    @Test func anUnboundedRowDoesNotLimitTheSides() {
        #expect(ControlsCentering.sideWidth(container: .infinity, center: 108, gap: 8) == .infinity)
    }
}
