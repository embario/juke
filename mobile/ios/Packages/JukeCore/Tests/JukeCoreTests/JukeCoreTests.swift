import XCTest
@testable import JukeCore

final class JukeCoreTests: XCTestCase {
    func testVersion() {
        XCTAssertEqual(JukeCoreVersion, "1.0.0")
    }
}
