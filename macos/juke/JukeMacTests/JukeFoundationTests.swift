import AppKit
import SwiftData
import XCTest
@testable import Juke

final class JukeSettingsTests: XCTestCase {
    private var suiteName = ""
    private var defaults: UserDefaults!

    override func setUp() {
        super.setUp()
        suiteName = "juke.settings.tests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        defaults = nil
        super.tearDown()
    }

    @MainActor
    func testDefaults() {
        let settings = JukeSettings(defaults: defaults)
        XCTAssertEqual(settings.appearance, .system)
        XCTAssertEqual(settings.crateFlipDirection, .sideToSide)
        XCTAssertEqual(settings.backendURL.absoluteString, "https://neptune.tail647b75.ts.net/")
        XCTAssertTrue(settings.backgroundRecognitionEnabled)
        XCTAssertTrue(settings.artworkTintEnabled)
    }

    @MainActor
    func testValuesPersistAcrossInstances() throws {
        let settings = JukeSettings(defaults: defaults)
        settings.appearance = .dark
        settings.crateFlipDirection = .frontToBack
        settings.backgroundRecognitionEnabled = false
        settings.artworkTintEnabled = false
        try settings.setBackendURL("https://juke-extra.example.test:8200/api/v1/")

        let reloaded = JukeSettings(defaults: defaults)
        XCTAssertEqual(reloaded.appearance, .dark)
        XCTAssertEqual(reloaded.crateFlipDirection, .frontToBack)
        XCTAssertFalse(reloaded.backgroundRecognitionEnabled)
        XCTAssertFalse(reloaded.artworkTintEnabled)
        XCTAssertEqual(reloaded.backendURL.absoluteString, "https://juke-extra.example.test:8200/")
        XCTAssertEqual(JukeServer.apiURL(defaults: defaults).absoluteString, "https://juke-extra.example.test:8200/api/v1/")
    }

    @MainActor
    func testUnknownStoredValuesFallBackToDefaults() {
        defaults.set("sepia", forKey: JukeSettings.Key.appearance)
        defaults.set("diagonal", forKey: JukeSettings.Key.crateFlip)
        defaults.set("ftp://nope", forKey: JukeSettings.Key.backendURL)
        let settings = JukeSettings(defaults: defaults)
        XCTAssertEqual(settings.appearance, .system)
        XCTAssertEqual(settings.crateFlipDirection, .sideToSide)
        XCTAssertEqual(settings.backendURL, JukeServer.defaultBaseURL)
    }

    @MainActor
    func testBackendChangesAreValidatedAndAnnouncedOnce() throws {
        let settings = JukeSettings(defaults: defaults)
        var announced: [URL] = []
        settings.onBackendURLChange = { announced.append($0) }

        XCTAssertThrowsError(try settings.setBackendURL("http://neptune.example")) // plain http off loopback
        XCTAssertThrowsError(try settings.setBackendURL("not a url"))
        XCTAssertThrowsError(try settings.setBackendURL("https://host.example/?token=1"))
        XCTAssertThrowsError(try settings.setBackendURL("https://user:pw@host.example/"))
        XCTAssertTrue(announced.isEmpty)

        XCTAssertTrue(try settings.setBackendURL("  HTTPS://Juke.Example.test  "))
        XCTAssertFalse(try settings.setBackendURL("https://juke.example.test/"), "same server is not a change")
        XCTAssertEqual(announced.map(\.absoluteString), ["https://juke.example.test/"])

        settings.resetBackendURL()
        XCTAssertEqual(settings.backendURL, JukeServer.defaultBaseURL)
        XCTAssertNil(defaults.string(forKey: JukeSettings.Key.backendURL), "the default is not stored")
        XCTAssertEqual(announced.count, 2)
    }

    @MainActor
    func testChangingTheServerSignsOutBeforeAnyRequestCanUseTheOldToken() async throws {
        let schema = Schema([ChatMessage.self])
        let container = try ModelContainer(for: schema, configurations: [ModelConfiguration("ServerChange", schema: schema, isStoredInMemoryOnly: true)])
        let settings = JukeSettings(defaults: defaults)
        let model = AppModel(container: container, settings: settings)
        model.session = JukeSession(account: .localPreview, accessToken: "old-server-token", authenticatedAt: .now)
        model.section = .chat
        model.coordinator.openNewStation()

        try settings.setBackendURL("https://other.example.test")

        // Synchronously, before any await: no session, no token for clients.
        XCTAssertNil(model.session)
        XCTAssertEqual(model.section, .radio)
        XCTAssertEqual(model.coordinator.radioRoute, .nowPlaying)
        do {
            _ = try await model.api.stations()
            XCTFail("The API must not have a token after the server changed")
        } catch let error as JukeAPIError {
            XCTAssertEqual(error, .notSignedIn)
        }
    }

    @MainActor
    func testServerNormalisation() {
        XCTAssertEqual(JukeServer.normalizedBaseURL("http://127.0.0.1:8000")?.absoluteString, "http://127.0.0.1:8000/")
        XCTAssertEqual(JukeServer.normalizedBaseURL("http://localhost:8000/juke")?.absoluteString, "http://localhost:8000/juke/")
        XCTAssertEqual(JukeServer.normalizedBaseURL("https://juke.example.test/api/v1")?.absoluteString, "https://juke.example.test/")
        XCTAssertEqual(JukeServer.normalizedBaseURL("https://juke.example.test/api/v1/")?.absoluteString, "https://juke.example.test/")
        XCTAssertEqual(JukeServer.normalizedBaseURL("https://juke.example.test/API/V1//")?.absoluteString, "https://juke.example.test/")
        XCTAssertEqual(JukeServer.normalizedBaseURL("https://juke.example.test/juke/api/v1/")?.absoluteString, "https://juke.example.test/juke/")
        XCTAssertNil(JukeServer.normalizedBaseURL("https://"))
        XCTAssertNil(JukeServer.normalizedBaseURL("https://host.example/#frag"))
    }

    @MainActor
    func testAppearanceMapsToAppKit() {
        XCTAssertNil(AppearanceChoice.system.nsAppearance)
        XCTAssertEqual(AppearanceChoice.light.nsAppearance?.name, .aqua)
        XCTAssertEqual(AppearanceChoice.dark.nsAppearance?.name, .darkAqua)
    }
}

final class JukeThemeTests: XCTestCase {
    /// Artwork colours from the design reference (`c1` of several tracks) plus
    /// the extremes the extractor can still produce after clamping.
    private let samples = [
        "#D9481C", "#8FB8A8", "#6C8EAD", "#E7A4B4", "#3B2A8F", "#1B1F3B", "#F2A7B5", "#2F4B7C",
        "#1F6F5C", "#B5532E", "#F2B33D", "#E9724C", "#6B2D5C", "#4C5B61", "#5C8001", "#1C2541",
        "#FFFFFF", "#000000", "#FF0000", "#00FF00", "#0000FF", "#FFFF00",
    ].map(RGB.init(hex:))

    func testMixMatchesThePrototype() {
        // Values computed with the prototype's JavaScript mix(a, b, t).
        XCTAssertEqual(RGB(hex: "#FFFFFF").mix(RGB(hex: "#D9481C"), 0.15).hex, "#F9E4DD")
        XCTAssertEqual(RGB(hex: "#1B1A18").mix(RGB(hex: "#D9481C"), 0.18).hex, "#3D2219")
        XCTAssertEqual(RGB(hex: "#121110").mix(RGB(hex: "#3B2A8F"), 0.08).hex, "#15131A")
        XCTAssertEqual(RGB(hex: "#000000").mix(RGB(hex: "#FFFFFF"), 0.5).hex, "#808080", "0.5 rounds up like Math.round")
        XCTAssertEqual(RGB(hex: "#123456").mix(RGB(hex: "#ABCDEF"), 0).hex, "#123456")
        XCTAssertEqual(RGB(hex: "#123456").mix(RGB(hex: "#ABCDEF"), 1).hex, "#ABCDEF")
    }

    func testPaletteTokensMatchTheReference() {
        let base = RGB(hex: "#D9481C")
        let light = JukeTheme.palette(dark: false, base: base)
        XCTAssertEqual(light.bg, RGB(hex: "#EFECE6").mix(base, 0.07))
        XCTAssertEqual(light.card, RGB(hex: "#FFFFFF").mix(base, 0.15))
        XCTAssertEqual(light.well, RGB(hex: "#FFFFFF").mix(base, 0.27))
        XCTAssertEqual(light.sleeveBack, RGB(hex: "#FFFFFF").mix(base, 0.08))
        XCTAssertEqual(light.ink.hex, "#1C1A17")
        XCTAssertEqual(light.sub.hex, "#4E4943")
        XCTAssertEqual(light.accent.hex, "#C2410C")
        XCTAssertEqual(light.accentSoft, RGB(hex: "#FFFFFF").mix(RGB(hex: "#C2410C"), 0.14))
        XCTAssertFalse(light.isDark)

        let dark = JukeTheme.palette(dark: true, base: base)
        XCTAssertEqual(dark.bg, RGB(hex: "#121110").mix(base, 0.08))
        XCTAssertEqual(dark.card, RGB(hex: "#1B1A18").mix(base, 0.18))
        XCTAssertEqual(dark.well, RGB(hex: "#1B1A18").mix(base, 0.28))
        XCTAssertEqual(dark.ink.hex, "#F3EFE8")
        XCTAssertEqual(dark.sub.hex, "#B8B1A7")
        XCTAssertEqual(dark.accent.hex, "#FB7A3C")
        XCTAssertEqual(dark.onAccent.hex, "#1A0D05")
        XCTAssertTrue(dark.isDark)
    }

    func testBrightArtworkGetsAGentlerTintOnlyWhereContrastNeedsIt() {
        let sunny = RGB(hex: "#F2B33D")
        let dark = JukeTheme.palette(dark: true, base: sunny)
        XCTAssertEqual(dark.card, RGB(hex: "#1B1A18").mix(sunny, 0.18), "card keeps the reference tint")
        XCTAssertNotEqual(dark.well, RGB(hex: "#1B1A18").mix(sunny, 0.28), "well tint is reduced")
        XCTAssertGreaterThanOrEqual(RGB.contrast(dark.sub, dark.well), 4.5)
        XCTAssertNotEqual(dark.well, RGB(hex: "#1B1A18"), "but still tinted")
    }

    func testContrastFormula() {
        XCTAssertEqual(RGB.contrast(RGB(hex: "#000000"), RGB(hex: "#FFFFFF")), 21, accuracy: 0.01)
        XCTAssertEqual(RGB.contrast(RGB(hex: "#777777"), RGB(hex: "#FFFFFF")), 4.48, accuracy: 0.01)
        XCTAssertEqual(RGB.contrast(RGB(hex: "#FFFFFF"), RGB(hex: "#777777")), RGB.contrast(RGB(hex: "#777777"), RGB(hex: "#FFFFFF")))
    }

    /// WCAG AA (4.5:1) for ink and sub text on the card, page and well, in both
    /// modes, for every sample artwork colour.
    func testTextMeetsWCAGAAOnEverySurface() {
        for dark in [false, true] {
            for base in samples {
                let theme = JukeTheme.palette(dark: dark, base: base)
                for (name, surface) in [("card", theme.card), ("bg", theme.bg), ("well", theme.well)] {
                    let ink = RGB.contrast(theme.ink, surface)
                    let sub = RGB.contrast(theme.sub, surface)
                    XCTAssertGreaterThanOrEqual(ink, 4.5, "ink on \(name), dark=\(dark), base=\(base)")
                    XCTAssertGreaterThanOrEqual(sub, 4.5, "sub on \(name), dark=\(dark), base=\(base)")
                }
                XCTAssertGreaterThanOrEqual(RGB.contrast(theme.onAccent, theme.accent), 4.5, "onAccent, dark=\(dark)")
            }
        }
    }

    func testHSLRoundTrip() {
        for color in samples {
            let hsl = color.hsl
            let back = RGB(hue: hsl.h, saturation: hsl.s, lightness: hsl.l)
            XCTAssertLessThanOrEqual(abs(Int(back.r) - Int(color.r)), 1, "\(color)")
            XCTAssertLessThanOrEqual(abs(Int(back.g) - Int(color.g)), 1, "\(color)")
            XCTAssertLessThanOrEqual(abs(Int(back.b) - Int(color.b)), 1, "\(color)")
        }
    }

    func testMotionRespectsReduceMotion() {
        XCTAssertNil(JukeMotion.navigationOut(reduceMotion: true))
        XCTAssertNil(JukeMotion.navigationIn(reduceMotion: true))
        XCTAssertNil(JukeMotion.control(reduceMotion: true))
        XCTAssertNotNil(JukeMotion.navigationOut(reduceMotion: false))
        XCTAssertNotNil(JukeMotion.navigationIn(reduceMotion: false))
        XCTAssertEqual(JukeMotion.navigationOutDuration, 0.2)
        XCTAssertEqual(JukeMotion.navigationInDuration, 0.48)
        XCTAssertEqual(JukeMotion.colorCrossfadeDuration, 0.9)
    }

    func testSectionsAndMiniPlayer() {
        XCTAssertEqual(JukeSection.allCases.map(\.title), ["Radio", "Library", "Memories", "Chat"])
        XCTAssertEqual(JukeSection.allCases.filter(\.showsMiniPlayer), [.library, .memories, .chat])
    }
}

final class ArtworkPaletteTests: XCTestCase {
    func testDominantColourPrefersTheColourfulAreaOverWhiteAndBlack() throws {
        // Half white, a quarter black, a quarter orange: the orange wins.
        let image = try makeImage { context, size in
            context.setFillColor(CGColor(srgbRed: 1, green: 1, blue: 1, alpha: 1))
            context.fill(CGRect(x: 0, y: 0, width: size, height: size / 2))
            context.setFillColor(CGColor(srgbRed: 0, green: 0, blue: 0, alpha: 1))
            context.fill(CGRect(x: 0, y: size / 2, width: size / 2, height: size / 2))
            context.setFillColor(CGColor(srgbRed: 0xD9 / 255, green: 0x48 / 255, blue: 0x1C / 255, alpha: 1))
            context.fill(CGRect(x: size / 2, y: size / 2, width: size / 2, height: size / 2))
        }
        let color = try XCTUnwrap(ArtworkPalette.dominantColor(of: image))
        XCTAssertGreaterThan(color.red, color.green + 0.3)
        XCTAssertGreaterThan(color.red, color.blue + 0.3)
    }

    func testGreysDoNotOutvoteASmallerColourfulArea() throws {
        // Three quarters mid grey, one quarter muted blue.
        let image = try makeImage { context, size in
            context.setFillColor(CGColor(srgbRed: 0.5, green: 0.5, blue: 0.52, alpha: 1))
            context.fill(CGRect(x: 0, y: 0, width: size, height: size))
            context.setFillColor(CGColor(srgbRed: 0x2F / 255, green: 0x4B / 255, blue: 0x7C / 255, alpha: 1))
            context.fill(CGRect(x: 0, y: 0, width: size / 2, height: size / 2))
        }
        let color = try XCTUnwrap(ArtworkPalette.dominantColor(of: image))
        XCTAssertGreaterThan(color.blue, color.red + 0.2)
        XCTAssertGreaterThan(color.hsl.s, 0.3)
    }

    @MainActor
    func testArtworkThatFailsToLoadFallsBackToNeutral() async throws {
        let palette = ArtworkPalette()
        palette.apply(RGB(hex: "#3B2A8F"))
        let missing = URL(fileURLWithPath: "/nonexistent/\(UUID().uuidString).jpg")
        palette.update(artworkURL: missing)
        for _ in 0..<100 where palette.base != JukeTheme.neutralBase {
            try await Task.sleep(for: .milliseconds(20))
        }
        XCTAssertEqual(palette.base, JukeTheme.neutralBase)
        // The URL is forgotten, so the same artwork is attempted again.
        palette.apply(RGB(hex: "#3B2A8F"))
        palette.update(artworkURL: missing)
        for _ in 0..<100 where palette.base != JukeTheme.neutralBase {
            try await Task.sleep(for: .milliseconds(20))
        }
        XCTAssertEqual(palette.base, JukeTheme.neutralBase)
    }

    func testAllWhiteArtIsPulledIntoAUsableBand() throws {
        let image = try makeImage { context, size in
            context.setFillColor(CGColor(srgbRed: 1, green: 1, blue: 1, alpha: 1))
            context.fill(CGRect(x: 0, y: 0, width: size, height: size))
        }
        let color = try XCTUnwrap(ArtworkPalette.dominantColor(of: image))
        XCTAssertLessThanOrEqual(color.hsl.l, 0.785)
    }

    func testUsableClampKeepsHueAndLightnessBand() {
        let pale = ArtworkPalette.usable(RGB(hex: "#FFF0F0"))
        XCTAssertLessThanOrEqual(pale.hsl.l, 0.785)
        XCTAssertGreaterThan(pale.red, pale.green)
        let deep = ArtworkPalette.usable(RGB(hex: "#05000A"))
        XCTAssertGreaterThanOrEqual(deep.hsl.l, 0.215)
        let fine = RGB(hex: "#D9481C")
        XCTAssertEqual(ArtworkPalette.usable(fine), fine)
    }

    @MainActor
    func testUpdateWithoutArtworkReturnsToNeutral() {
        let palette = ArtworkPalette()
        palette.apply(RGB(hex: "#3B2A8F"))
        XCTAssertEqual(palette.base, RGB(hex: "#3B2A8F"))
        palette.update(artworkURL: nil)
        XCTAssertEqual(palette.base, JukeTheme.neutralBase)
        palette.apply(RGB(hex: "#3B2A8F"))
        palette.update(artworkURL: URL(string: "https://example.test/art.jpg"), enabled: false)
        XCTAssertEqual(palette.base, JukeTheme.neutralBase)
    }

    private func makeImage(size: Int = 64, draw: (CGContext, CGFloat) -> Void) throws -> CGImage {
        let context = try XCTUnwrap(CGContext(
            data: nil, width: size, height: size, bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ))
        draw(context, CGFloat(size))
        return try XCTUnwrap(context.makeImage())
    }
}
