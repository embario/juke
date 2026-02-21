import XCTest
@testable import JukeKit

final class JukeKitFlashOverlayTests: XCTestCase {

    @MainActor
    func testFlashCenterAutoDismissesMessage() async {
        let center = JukeKitFlashCenter()

        center.show("Saved", variant: .success, duration: 0.01)
        XCTAssertEqual(center.message?.text, "Saved")

        await waitUntil(
            timeoutNanoseconds: 400_000_000,
            pollIntervalNanoseconds: 10_000_000
        ) {
            center.message == nil
        }
        XCTAssertNil(center.message)
    }

    @MainActor
    func testLatestMessageWinsWhenShowingBackToBack() async {
        let center = JukeKitFlashCenter()

        center.show("First", duration: 0.01)
        center.show("Second", variant: .warning, duration: 0.08)

        await waitUntil(
            timeoutNanoseconds: 300_000_000,
            pollIntervalNanoseconds: 10_000_000
        ) {
            center.message?.text == "Second"
        }
        XCTAssertEqual(center.message?.text, "Second")

        await waitUntil(
            timeoutNanoseconds: 600_000_000,
            pollIntervalNanoseconds: 10_000_000
        ) {
            center.message == nil
        }
        XCTAssertNil(center.message)
    }

    @MainActor
    private func waitUntil(
        timeoutNanoseconds: UInt64,
        pollIntervalNanoseconds: UInt64,
        condition: () -> Bool
    ) async {
        let deadline = ContinuousClock.now + .nanoseconds(Int64(timeoutNanoseconds))
        while ContinuousClock.now < deadline {
            if condition() {
                return
            }
            try? await Task.sleep(nanoseconds: pollIntervalNanoseconds)
        }
    }
}
