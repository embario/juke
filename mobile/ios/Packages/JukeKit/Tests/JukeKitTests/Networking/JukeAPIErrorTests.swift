import XCTest
@testable import JukeKit

final class JukeAPIErrorTests: XCTestCase {

    func testErrorDescriptions() {
        XCTAssertEqual(JukeAPIError.invalidURL.errorDescription, "Could not build API request.")
        XCTAssertEqual(JukeAPIError.invalidResponse.errorDescription, "Received an invalid response from the server.")
        XCTAssertEqual(JukeAPIError.unauthorized.errorDescription, "Session expired. Please log in again.")
        XCTAssertEqual(JukeAPIError.server(status: 500, message: "Server error").errorDescription, "Server error")
        XCTAssertEqual(JukeAPIError.decoding("Parse failed").errorDescription, "Unable to parse server response: Parse failed")
        XCTAssertEqual(JukeAPIError.networkError("No connection").errorDescription, "No connection")
    }

    func testEquality() {
        XCTAssertEqual(JukeAPIError.invalidURL, JukeAPIError.invalidURL)
        XCTAssertEqual(JukeAPIError.invalidResponse, JukeAPIError.invalidResponse)
        XCTAssertEqual(JukeAPIError.unauthorized, JukeAPIError.unauthorized)
        XCTAssertEqual(
            JukeAPIError.server(status: 404, message: "Not found"),
            JukeAPIError.server(status: 404, message: "Not found")
        )
        XCTAssertNotEqual(
            JukeAPIError.server(status: 404, message: "Not found"),
            JukeAPIError.server(status: 500, message: "Not found")
        )
        XCTAssertNotEqual(JukeAPIError.invalidURL, JukeAPIError.invalidResponse)
    }
}
