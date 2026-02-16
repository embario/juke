import Foundation

/// App-level configuration settings.
///
/// Reads configuration from environment variables and Info.plist.
/// Environment variables take precedence over plist values.
public struct JukeAppConfiguration: Sendable {
    /// Shared singleton instance using default bundle and process info.
    public static let shared = JukeAppConfiguration()

    /// Whether registration is disabled for this app.
    ///
    /// When `true`, the app should hide or disable registration UI and
    /// redirect users to register via the main Juke app or web.
    public let isRegistrationDisabled: Bool

    /// Creates a configuration from the given bundle and process info.
    /// - Parameters:
    ///   - bundle: Bundle to read plist values from. Defaults to `.main`.
    ///   - processInfo: Process info to read environment from. Defaults to `.processInfo`.
    public init(bundle: Bundle = .main, processInfo: ProcessInfo = .processInfo) {
        let plistValue = bundle.object(forInfoDictionaryKey: "DISABLE_REGISTRATION")
        self.init(environment: processInfo.environment, plistValue: plistValue)
    }

    /// Creates a configuration with explicit values.
    /// - Parameters:
    ///   - environment: Environment dictionary (typically from ProcessInfo).
    ///   - plistValue: Value from Info.plist (can be String or Bool).
    public init(environment: [String: String], plistValue: Any?) {
        // Check environment first
        if let envValue = environment["DISABLE_REGISTRATION"] {
            isRegistrationDisabled = Self.parseFlag(envValue)
            return
        }

        // Check plist as String
        if let plistString = plistValue as? String {
            isRegistrationDisabled = Self.parseFlag(plistString)
            return
        }

        // Check plist as Bool
        if let plistBool = plistValue as? Bool {
            isRegistrationDisabled = plistBool
            return
        }

        // Default: registration enabled
        isRegistrationDisabled = false
    }

    /// Creates a configuration with an explicit value.
    /// - Parameter isRegistrationDisabled: Whether registration is disabled.
    public init(isRegistrationDisabled: Bool) {
        self.isRegistrationDisabled = isRegistrationDisabled
    }

    /// Parses a string flag value to a boolean.
    ///
    /// Recognizes: "1", "true", "yes", "on" (case-insensitive) as `true`.
    /// - Parameter value: The string value to parse.
    /// - Returns: `true` if the value indicates the flag is enabled.
    private static func parseFlag(_ value: String) -> Bool {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return ["1", "true", "yes", "on"].contains(normalized)
    }
}
