import XCTest
@testable import JukeCore

final class JukeDeepLinkTests: XCTestCase {

    // MARK: - Parser Setup

    private func makeParser() -> JukeDeepLinkParser {
        JukeDeepLinkParser(
            schemes: ["juke", "shotclock", "tunetrivia"],
            universalLinkHosts: ["juke.fm", "www.juke.fm"]
        )
    }

    // MARK: - Custom Scheme Tests

    func testParseVerifyUserCustomScheme() {
        let parser = makeParser()
        let url = URL(string: "juke://verify-user?user_id=123&timestamp=abc&signature=xyz")!

        let result = parser.parse(url)

        XCTAssertEqual(result, .verifyUser(userId: "123", timestamp: "abc", signature: "xyz"))
    }

    func testParseRegisterCustomScheme() {
        let parser = makeParser()
        let url = URL(string: "juke://register")!

        let result = parser.parse(url)

        XCTAssertEqual(result, .register)
    }

    func testParseCustomSchemeUnknownAction() {
        let parser = makeParser()
        let url = URL(string: "juke://some-action?foo=bar")!

        let result = parser.parse(url)

        XCTAssertEqual(result, .custom(host: "some-action", path: "", queryItems: ["foo": "bar"]))
    }

    func testParseVerifyUserDifferentScheme() {
        let parser = makeParser()
        let url = URL(string: "shotclock://verify-user?user_id=456&timestamp=def&signature=uvw")!

        let result = parser.parse(url)

        XCTAssertEqual(result, .verifyUser(userId: "456", timestamp: "def", signature: "uvw"))
    }

    // MARK: - Universal Link Tests

    func testParseVerifyUserUniversalLink() {
        let parser = makeParser()
        let url = URL(string: "https://juke.fm/verify-user?user_id=789&timestamp=ghi&signature=rst")!

        let result = parser.parse(url)

        XCTAssertEqual(result, .verifyUser(userId: "789", timestamp: "ghi", signature: "rst"))
    }

    func testParseUniversalLinkWwwSubdomain() {
        let parser = makeParser()
        let url = URL(string: "https://www.juke.fm/verify-user?user_id=111&timestamp=jkl&signature=mno")!

        let result = parser.parse(url)

        XCTAssertEqual(result, .verifyUser(userId: "111", timestamp: "jkl", signature: "mno"))
    }

    func testParseRegisterUniversalLink() {
        let parser = makeParser()
        let url = URL(string: "https://juke.fm/register")!

        let result = parser.parse(url)

        XCTAssertEqual(result, .register)
    }

    // MARK: - Invalid URL Tests

    func testParseUnknownScheme() {
        let parser = makeParser()
        let url = URL(string: "unknown://verify-user?user_id=123&timestamp=abc&signature=xyz")!

        let result = parser.parse(url)

        XCTAssertNil(result)
    }

    func testParseUnknownHost() {
        let parser = makeParser()
        let url = URL(string: "https://unknown.com/verify-user?user_id=123&timestamp=abc&signature=xyz")!

        let result = parser.parse(url)

        XCTAssertNil(result)
    }

    func testParseVerifyUserMissingParams() {
        let parser = makeParser()
        let url = URL(string: "juke://verify-user?user_id=123")!

        let result = parser.parse(url)

        XCTAssertNil(result)
    }

    func testParseVerifyUserMissingUserId() {
        let parser = makeParser()
        let url = URL(string: "juke://verify-user?timestamp=abc&signature=xyz")!

        let result = parser.parse(url)

        XCTAssertNil(result)
    }

    // MARK: - URLComponents Extension Tests

    func testQueryParametersExtension() {
        let url = URL(string: "https://example.com/path?foo=bar&baz=qux")!
        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)!

        let params = components.queryParameters

        XCTAssertEqual(params["foo"], "bar")
        XCTAssertEqual(params["baz"], "qux")
    }

    func testQueryParametersEmpty() {
        let url = URL(string: "https://example.com/path")!
        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)!

        let params = components.queryParameters

        XCTAssertTrue(params.isEmpty)
    }

    // MARK: - Deep Link Equality Tests

    func testDeepLinkEquality() {
        let link1 = JukeDeepLink.verifyUser(userId: "1", timestamp: "a", signature: "x")
        let link2 = JukeDeepLink.verifyUser(userId: "1", timestamp: "a", signature: "x")
        let link3 = JukeDeepLink.verifyUser(userId: "2", timestamp: "a", signature: "x")

        XCTAssertEqual(link1, link2)
        XCTAssertNotEqual(link1, link3)
    }

    func testDeepLinkRegisterEquality() {
        XCTAssertEqual(JukeDeepLink.register, JukeDeepLink.register)
    }
}
