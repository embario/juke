import XCTest
@testable import JukeKit

final class JukeAPIConfigurationTests: XCTestCase {

    func testInitFromEnvironment() {
        let config = JukeAPIConfiguration(
            environment: ["BACKEND_URL": "https://api.test.com"],
            backendPlist: nil
        )
        XCTAssertEqual(config.baseURL.absoluteString, "https://api.test.com")
    }

    func testInitFromPlist() {
        let config = JukeAPIConfiguration(
            environment: [:],
            backendPlist: "https://api.plist.com"
        )
        XCTAssertEqual(config.baseURL.absoluteString, "https://api.plist.com")
    }

    func testEnvironmentTakesPrecedenceOverPlist() {
        let config = JukeAPIConfiguration(
            environment: ["BACKEND_URL": "https://api.env.com"],
            backendPlist: "https://api.plist.com"
        )
        XCTAssertEqual(config.baseURL.absoluteString, "https://api.env.com")
    }

    func testFrontendURLFromEnvironment() {
        let config = JukeAPIConfiguration(
            environment: [
                "BACKEND_URL": "https://api.test.com",
                "FRONTEND_URL": "https://web.test.com"
            ],
            backendPlist: nil
        )
        XCTAssertEqual(config.frontendURL?.absoluteString, "https://web.test.com")
    }

    func testFrontendURLFallsBackToBaseURL() {
        let config = JukeAPIConfiguration(
            environment: ["BACKEND_URL": "https://api.test.com"],
            backendPlist: nil
        )
        XCTAssertEqual(config.frontendURL?.absoluteString, "https://api.test.com")
    }

    func testDirectInitialization() {
        let baseURL = URL(string: "https://api.direct.com")!
        let frontendURL = URL(string: "https://web.direct.com")!
        let config = JukeAPIConfiguration(baseURL: baseURL, frontendURL: frontendURL)

        XCTAssertEqual(config.baseURL, baseURL)
        XCTAssertEqual(config.frontendURL, frontendURL)
    }

    func testEmptyEnvironmentValueIgnored() {
        let config = JukeAPIConfiguration(
            environment: ["BACKEND_URL": ""],
            backendPlist: "https://api.plist.com"
        )
        XCTAssertEqual(config.baseURL.absoluteString, "https://api.plist.com")
    }
}
