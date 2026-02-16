import XCTest
@testable import JukeCore

final class JukeAppConfigurationTests: XCTestCase {

    func testRegistrationEnabledByDefault() {
        let config = JukeAppConfiguration(environment: [:], plistValue: nil)
        XCTAssertFalse(config.isRegistrationDisabled)
    }

    func testRegistrationDisabledFromEnvironment() {
        let config = JukeAppConfiguration(
            environment: ["DISABLE_REGISTRATION": "1"],
            plistValue: nil
        )
        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testRegistrationDisabledFromEnvironmentTrue() {
        let config = JukeAppConfiguration(
            environment: ["DISABLE_REGISTRATION": "true"],
            plistValue: nil
        )
        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testRegistrationDisabledFromEnvironmentYes() {
        let config = JukeAppConfiguration(
            environment: ["DISABLE_REGISTRATION": "YES"],
            plistValue: nil
        )
        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testRegistrationDisabledFromEnvironmentOn() {
        let config = JukeAppConfiguration(
            environment: ["DISABLE_REGISTRATION": "on"],
            plistValue: nil
        )
        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testRegistrationEnabledFromEnvironmentZero() {
        let config = JukeAppConfiguration(
            environment: ["DISABLE_REGISTRATION": "0"],
            plistValue: nil
        )
        XCTAssertFalse(config.isRegistrationDisabled)
    }

    func testRegistrationEnabledFromEnvironmentFalse() {
        let config = JukeAppConfiguration(
            environment: ["DISABLE_REGISTRATION": "false"],
            plistValue: nil
        )
        XCTAssertFalse(config.isRegistrationDisabled)
    }

    func testRegistrationDisabledFromPlistString() {
        let config = JukeAppConfiguration(
            environment: [:],
            plistValue: "1"
        )
        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testRegistrationDisabledFromPlistBool() {
        let config = JukeAppConfiguration(
            environment: [:],
            plistValue: true
        )
        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testRegistrationEnabledFromPlistBool() {
        let config = JukeAppConfiguration(
            environment: [:],
            plistValue: false
        )
        XCTAssertFalse(config.isRegistrationDisabled)
    }

    func testEnvironmentTakesPrecedenceOverPlist() {
        // Environment says enabled (0), plist says disabled (true)
        let config = JukeAppConfiguration(
            environment: ["DISABLE_REGISTRATION": "0"],
            plistValue: true
        )
        XCTAssertFalse(config.isRegistrationDisabled)
    }

    func testDirectInitialization() {
        let enabled = JukeAppConfiguration(isRegistrationDisabled: false)
        XCTAssertFalse(enabled.isRegistrationDisabled)

        let disabled = JukeAppConfiguration(isRegistrationDisabled: true)
        XCTAssertTrue(disabled.isRegistrationDisabled)
    }

    func testWhitespaceHandling() {
        let config = JukeAppConfiguration(
            environment: ["DISABLE_REGISTRATION": "  true  "],
            plistValue: nil
        )
        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testCaseInsensitivity() {
        let config = JukeAppConfiguration(
            environment: ["DISABLE_REGISTRATION": "TRUE"],
            plistValue: nil
        )
        XCTAssertTrue(config.isRegistrationDisabled)
    }
}
