import XCTest
import JukeKit
@testable import ShotClock

final class ShotClockTests: XCTestCase {

    func testAPIClientBaseURL() {
        let config = JukeAPIConfiguration(baseURL: URL(string: "http://test.example.com")!)
        let client = JukeAPIClient(configuration: config)
        XCTAssertEqual(client.baseURL.absoluteString, "http://test.example.com")
    }

    func testUserProfilePreferredName_withDisplayName() {
        let profile = UserProfile(id: 1, username: "user1", displayName: "Display", bio: nil, avatarUrl: nil)
        XCTAssertEqual(profile.preferredName, "Display")
    }

    func testUserProfilePreferredName_withoutDisplayName() {
        let profile = UserProfile(id: 1, username: "user1", displayName: nil, bio: nil, avatarUrl: nil)
        XCTAssertEqual(profile.preferredName, "user1")
    }

    func testUserProfilePreferredName_emptyDisplayName() {
        let profile = UserProfile(id: 1, username: "user1", displayName: "", bio: nil, avatarUrl: nil)
        XCTAssertEqual(profile.preferredName, "user1")
    }

    func testLoginRequestEncoding() throws {
        let request = LoginRequest(username: "test", password: "pass123")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(request)
        let dict = try JSONSerialization.jsonObject(with: data) as? [String: String]
        XCTAssertEqual(dict?["username"], "test")
        XCTAssertEqual(dict?["password"], "pass123")
    }

    func testRegisterRequestEncoding() throws {
        let request = RegisterRequest(username: "new", email: "a@b.com", password: "pass1234", passwordConfirm: "pass1234")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(request)
        let dict = try JSONSerialization.jsonObject(with: data) as? [String: String]
        XCTAssertEqual(dict?["username"], "new")
        XCTAssertEqual(dict?["email"], "a@b.com")
        XCTAssertEqual(dict?["password_confirm"], "pass1234")
    }

    func testAppConfigurationEnvOverridesPlist() {
        let config = JukeAppConfiguration(
            environment: ["DISABLE_REGISTRATION": "yes"],
            plistValue: "false"
        )

        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testAppConfigurationPlistBooleanFallback() {
        let config = JukeAppConfiguration(
            environment: [:],
            plistValue: true
        )

        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testResolveBaseURLUsesEnvironment() {
        let config = JukeAPIConfiguration(
            environment: ["BACKEND_URL": "http://env.example.com"],
            backendPlist: "http://plist.example.com"
        )

        XCTAssertEqual(config.baseURL.absoluteString, "http://env.example.com")
    }

    func testResolveBaseURLUsesPlistWhenEnvironmentMissing() {
        let config = JukeAPIConfiguration(
            environment: [:],
            backendPlist: "http://plist.example.com"
        )

        XCTAssertEqual(config.baseURL.absoluteString, "http://plist.example.com")
    }
}
