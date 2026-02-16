import Foundation

/// Configuration for the Juke API client.
///
/// Reads `BACKEND_URL` and `FRONTEND_URL` from environment variables or Info.plist.
/// Environment variables take precedence over plist values.
public struct JukeAPIConfiguration {
    /// Shared singleton instance using default bundle and process info.
    public static let shared = JukeAPIConfiguration()

    /// Base URL for API requests.
    public let baseURL: URL

    /// Frontend URL for web fallback (e.g., registration).
    public let frontendURL: URL?

    /// Creates a configuration from the given bundle and process info.
    /// - Parameters:
    ///   - bundle: Bundle to read plist values from. Defaults to `.main`.
    ///   - processInfo: Process info to read environment from. Defaults to `.processInfo`.
    public init(bundle: Bundle = .main, processInfo: ProcessInfo = .processInfo) {
        let backendPlist = bundle.object(forInfoDictionaryKey: "BACKEND_URL") as? String
        let frontendPlist = bundle.object(forInfoDictionaryKey: "FRONTEND_URL") as? String
        self.init(
            environment: processInfo.environment,
            backendPlist: backendPlist,
            frontendPlist: frontendPlist
        )
    }

    /// Creates a configuration with explicit values.
    /// - Parameters:
    ///   - environment: Environment dictionary (typically from ProcessInfo).
    ///   - backendPlist: Backend URL from Info.plist.
    ///   - frontendPlist: Frontend URL from Info.plist.
    public init(environment: [String: String], backendPlist: String?, frontendPlist: String? = nil) {
        // Resolve backend URL (required)
        if let overrideURLString = environment["BACKEND_URL"],
           !overrideURLString.isEmpty,
           let url = URL(string: overrideURLString) {
            baseURL = url
        } else if let backendPlist,
                  !backendPlist.isEmpty,
                  let url = URL(string: backendPlist) {
            baseURL = url
        } else {
            fatalError("BACKEND_URL must be set in the environment or Info.plist.")
        }

        // Resolve frontend URL (optional, falls back to baseURL)
        if let overrideURLString = environment["FRONTEND_URL"],
           !overrideURLString.isEmpty,
           let url = URL(string: overrideURLString) {
            frontendURL = url
        } else if let frontendPlist,
                  !frontendPlist.isEmpty,
                  let url = URL(string: frontendPlist) {
            frontendURL = url
        } else {
            // Default: assume frontend is served from the same origin as backend
            frontendURL = baseURL
        }
    }

    /// Creates a configuration with explicit URLs.
    /// - Parameters:
    ///   - baseURL: Base URL for API requests.
    ///   - frontendURL: Frontend URL for web fallback.
    public init(baseURL: URL, frontendURL: URL? = nil) {
        self.baseURL = baseURL
        self.frontendURL = frontendURL ?? baseURL
    }
}
