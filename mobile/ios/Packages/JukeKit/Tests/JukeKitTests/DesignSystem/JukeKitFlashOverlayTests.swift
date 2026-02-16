import XCTest
@testable import JukeKit

final class JukeKitFlashOverlayTests: XCTestCase {

    @MainActor
    func testFlashCenterAutoDismissesMessage() async {
        let center = JukeKitFlashCenter()

        center.show("Saved", variant: .success, duration: 0.01)
        XCTAssertEqual(center.message?.text, "Saved")

        try? await Task.sleep(nanoseconds: 80_000_000)

        XCTAssertNil(center.message)
    }

    @MainActor
    func testLatestMessageWinsWhenShowingBackToBack() async {
        let center = JukeKitFlashCenter()

        center.show("First", duration: 0.01)
        center.show("Second", variant: .warning, duration: 0.08)

        try? await Task.sleep(nanoseconds: 30_000_000)
        XCTAssertEqual(center.message?.text, "Second")

        try? await Task.sleep(nanoseconds: 90_000_000)
        XCTAssertNil(center.message)
    }
}
