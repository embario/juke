import AppKit
import Foundation
import Observation
import SwiftUI

/// Light, Dark, or follow macOS.
enum AppearanceChoice: String, CaseIterable, Identifiable, Sendable {
    case system, light, dark

    var id: String { rawValue }

    var label: String {
        switch self {
        case .system: "Match system"
        case .light: "Light"
        case .dark: "Dark"
        }
    }

    var symbol: String {
        switch self {
        case .system: "circle.lefthalf.filled"
        case .light: "sun.max"
        case .dark: "moon"
        }
    }

    /// The AppKit appearance applied to every window; `nil` follows the system.
    var nsAppearance: NSAppearance? {
        switch self {
        case .system: nil
        case .light: NSAppearance(named: .aqua)
        case .dark: NSAppearance(named: .darkAqua)
        }
    }
}

/// How records move when flipping through the Library crate.
enum CrateFlipDirection: String, CaseIterable, Identifiable, Sendable {
    case sideToSide, frontToBack

    var id: String { rawValue }

    var label: String {
        switch self {
        case .sideToSide: "Side to side"
        case .frontToBack: "Front to back"
        }
    }
}

/// App-wide preferences, persisted in `UserDefaults`.
///
/// Views read it with `@Environment(JukeSettings.self)`; write through a
/// `Bindable(settings)`. Non-UI code that only needs the backend URL uses
/// `JukeServer`, which reads the same key.
@MainActor
@Observable
final class JukeSettings {
    enum Key {
        static let appearance = "juke.settings.appearance"
        static let crateFlip = "juke.settings.crateFlipDirection"
        static let backendURL = JukeServer.backendURLKey
        static let backgroundRecognition = "juke.settings.backgroundRecognition"
        static let artworkTint = "juke.settings.artworkTint"
    }

    enum BackendURLError: LocalizedError, Equatable {
        case invalid
        var errorDescription: String? {
            "Enter an https:// address, for example \(JukeServer.defaultBaseURL.absoluteString)"
        }
    }

    var appearance: AppearanceChoice {
        didSet { defaults.set(appearance.rawValue, forKey: Key.appearance) }
    }

    var crateFlipDirection: CrateFlipDirection {
        didSet { defaults.set(crateFlipDirection.rawValue, forKey: Key.crateFlip) }
    }

    /// Whether Juke may identify music in the background (player metadata and
    /// Shazam) to feed taste signals. S5 owns the background recognizer and
    /// must check this before starting it.
    var backgroundRecognitionEnabled: Bool {
        didSet { defaults.set(backgroundRecognitionEnabled, forKey: Key.backgroundRecognition) }
    }

    /// Whether page and card colours follow the current album art.
    var artworkTintEnabled: Bool {
        didSet { defaults.set(artworkTintEnabled, forKey: Key.artworkTint) }
    }

    /// The backend root. Change it with `setBackendURL(_:)`.
    private(set) var backendURL: URL

    /// Called after the backend URL changes. The app signs out here, because an
    /// access token belongs to the server that issued it.
    @ObservationIgnored var onBackendURLChange: (@MainActor (URL) -> Void)?

    @ObservationIgnored let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        appearance = defaults.string(forKey: Key.appearance).flatMap(AppearanceChoice.init(rawValue:)) ?? .system
        crateFlipDirection = defaults.string(forKey: Key.crateFlip).flatMap(CrateFlipDirection.init(rawValue:)) ?? .sideToSide
        backgroundRecognitionEnabled = defaults.object(forKey: Key.backgroundRecognition) as? Bool ?? true
        artworkTintEnabled = defaults.object(forKey: Key.artworkTint) as? Bool ?? true
        backendURL = JukeServer.baseURL(defaults: defaults)
    }

    /// Validates, stores and announces a new backend URL. Returns whether the
    /// stored value changed.
    @discardableResult
    func setBackendURL(_ text: String) throws(BackendURLError) -> Bool {
        guard let url = JukeServer.normalizedBaseURL(text) else { throw .invalid }
        guard url != backendURL else { return false }
        backendURL = url
        if url == JukeServer.defaultBaseURL {
            defaults.removeObject(forKey: Key.backendURL)
        } else {
            defaults.set(url.absoluteString, forKey: Key.backendURL)
        }
        onBackendURLChange?(url)
        return true
    }

    func resetBackendURL() {
        try? setBackendURL(JukeServer.defaultBaseURL.absoluteString)
    }
}
