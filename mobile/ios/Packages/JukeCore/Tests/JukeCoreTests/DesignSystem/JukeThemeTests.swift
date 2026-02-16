import XCTest
import SwiftUI
@testable import JukeCore

final class JukeThemeTests: XCTestCase {

    // MARK: - Built-in Theme Tests

    func testJukeDefaultThemeColors() {
        let theme = JukeDefaultTheme()

        // Verify non-nil colors
        XCTAssertNotNil(theme.background)
        XCTAssertNotNil(theme.panel)
        XCTAssertNotNil(theme.panelAlt)
        XCTAssertNotNil(theme.accent)
        XCTAssertNotNil(theme.accentSoft)
        XCTAssertNotNil(theme.text)
        XCTAssertNotNil(theme.muted)
        XCTAssertNotNil(theme.border)
        XCTAssertNotNil(theme.success)
        XCTAssertNotNil(theme.warning)
        XCTAssertNotNil(theme.error)
        XCTAssertNotNil(theme.primaryButtonForeground)
    }

    func testShotClockThemeColors() {
        let theme = ShotClockTheme()

        XCTAssertNotNil(theme.background)
        XCTAssertNotNil(theme.panel)
        XCTAssertNotNil(theme.accent)
        XCTAssertNotNil(theme.secondary)
        XCTAssertNotNil(theme.text)
    }

    func testTuneTriviaThemeColors() {
        let theme = TuneTriviaTheme()

        XCTAssertNotNil(theme.background)
        XCTAssertNotNil(theme.panel)
        XCTAssertNotNil(theme.accent)
        XCTAssertNotNil(theme.secondary)
        XCTAssertNotNil(theme.text)
    }

    // MARK: - Default Implementation Tests

    func testSecondaryDefaultsToAccent() {
        // Create a custom theme that only implements required properties
        struct MinimalTheme: JukeTheme {
            let background = Color.black
            let panel = Color.gray
            let panelAlt = Color.gray.opacity(0.5)
            let accent = Color.orange
            let accentSoft = Color.orange.opacity(0.7)
            let text = Color.white
            let muted = Color.gray
            let border = Color.white.opacity(0.1)
            let success = Color.green
            let warning = Color.yellow
            let error = Color.red
        }

        let theme = MinimalTheme()
        // secondary should default to accent
        XCTAssertEqual(theme.secondary.description, theme.accent.description)
    }

    // MARK: - Color Extension Tests

    func testColorHexSixDigits() {
        let color = Color(hex: "#FF5733")
        // Just verify it doesn't crash and returns a color
        XCTAssertNotNil(color)
    }

    func testColorHexThreeDigits() {
        let color = Color(hex: "#F53")
        XCTAssertNotNil(color)
    }

    func testColorHexWithoutHash() {
        let color = Color(hex: "FF5733")
        XCTAssertNotNil(color)
    }

    func testColorHexLowercase() {
        let color = Color(hex: "#ff5733")
        XCTAssertNotNil(color)
    }

    func testColorHexBlack() {
        let color = Color(hex: "#000000")
        XCTAssertNotNil(color)
    }

    func testColorHexWhite() {
        let color = Color(hex: "#FFFFFF")
        XCTAssertNotNil(color)
    }

    // MARK: - Theme Conformance Tests

    func testJukeDefaultThemeConformsToProtocol() {
        let theme: JukeTheme = JukeDefaultTheme()
        XCTAssertNotNil(theme.background)
    }

    func testShotClockThemeConformsToProtocol() {
        let theme: JukeTheme = ShotClockTheme()
        XCTAssertNotNil(theme.background)
    }

    func testTuneTriviaThemeConformsToProtocol() {
        let theme: JukeTheme = TuneTriviaTheme()
        XCTAssertNotNil(theme.background)
    }
}
