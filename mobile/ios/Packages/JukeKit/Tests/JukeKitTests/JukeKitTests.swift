import XCTest
@testable import JukeKit

final class JukeKitTests: XCTestCase {
    func testVersion() {
        XCTAssertEqual(JukeKitVersion, "1.0.0")
    }
}
