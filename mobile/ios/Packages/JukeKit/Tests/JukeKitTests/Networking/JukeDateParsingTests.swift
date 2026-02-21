import XCTest
@testable import JukeKit

final class JukeDateParsingTests: XCTestCase {

    func testParseWithFractionalSeconds() {
        let dateString = "2026-01-15T10:30:00.123Z"
        let date = JukeDateParsing.parse(dateString)

        XCTAssertNotNil(date)

        let calendar = Calendar(identifier: .gregorian)
        let components = calendar.dateComponents(in: TimeZone(identifier: "UTC")!, from: date!)
        XCTAssertEqual(components.year, 2026)
        XCTAssertEqual(components.month, 1)
        XCTAssertEqual(components.day, 15)
        XCTAssertEqual(components.hour, 10)
        XCTAssertEqual(components.minute, 30)
        XCTAssertEqual(components.second, 0)
    }

    func testParseWithoutFractionalSeconds() {
        let dateString = "2026-01-15T10:30:00Z"
        let date = JukeDateParsing.parse(dateString)

        XCTAssertNotNil(date)
    }

    func testParseWithMicroseconds() {
        let dateString = "2026-01-15T10:30:00.123456Z"
        let date = JukeDateParsing.parse(dateString)

        XCTAssertNotNil(date)
    }

    func testParseWithTimezoneOffset() {
        let dateString = "2026-01-15T10:30:00.123456+00:00"
        let date = JukeDateParsing.parse(dateString)

        XCTAssertNotNil(date)
    }

    func testParseInvalidDate() {
        let dateString = "not-a-date"
        let date = JukeDateParsing.parse(dateString)

        XCTAssertNil(date)
    }

    func testMakeDecoder() {
        let decoder = JukeDateParsing.makeDecoder()
        XCTAssertNotNil(decoder)
    }

    func testDecoderWithValidDate() throws {
        struct TestModel: Decodable {
            let createdAt: Date
        }

        let json = """
        {"createdAt": "2026-01-15T10:30:00.123Z"}
        """.data(using: .utf8)!

        let decoder = JukeDateParsing.makeDecoder()
        let model = try decoder.decode(TestModel.self, from: json)

        XCTAssertNotNil(model.createdAt)
    }

    func testDecoderWithInvalidDateThrows() {
        struct TestModel: Decodable {
            let createdAt: Date
        }

        let json = """
        {"createdAt": "invalid-date"}
        """.data(using: .utf8)!

        let decoder = JukeDateParsing.makeDecoder()

        XCTAssertThrowsError(try decoder.decode(TestModel.self, from: json))
    }

    func testDecoderParsesDatesWithCustomCodingKeys() throws {
        struct TestModel: Decodable {
            let inviteCode: String
            let tracksPerPlayer: Int
            let createdAt: Date

            enum CodingKeys: String, CodingKey {
                case inviteCode
                case tracksPerPlayer
                case createdAt
            }
        }

        let json = """
        {
            "invite_code": "ABCD1234",
            "tracks_per_player": 3,
            "created_at": "2026-01-15T10:30:00.123Z"
        }
        """.data(using: .utf8)!

        let decoder = JukeDateParsing.makeDecoder()
        let model = try decoder.decode(TestModel.self, from: json)

        XCTAssertEqual(model.inviteCode, "ABCD1234")
        XCTAssertEqual(model.tracksPerPlayer, 3)
        XCTAssertNotNil(model.createdAt)
    }

    func testDecoderConvertsSnakeCaseToCamelCaseWithoutCustomCodingKeys() throws {
        struct TestModel: Decodable {
            let inviteCode: String
            let tracksPerPlayer: Int
        }

        let json = """
        {
            "invite_code": "ABCD1234",
            "tracks_per_player": 3
        }
        """.data(using: .utf8)!

        let decoder = JukeDateParsing.makeDecoder()
        let model = try decoder.decode(TestModel.self, from: json)

        XCTAssertEqual(model.inviteCode, "ABCD1234")
        XCTAssertEqual(model.tracksPerPlayer, 3)
    }
}
