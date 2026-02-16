import Foundation

/// Represents a parsed deep link for Juke apps.
public enum JukeDeepLink: Equatable {
    /// Email verification link with user verification parameters.
    /// - Parameters:
    ///   - userId: The user ID to verify.
    ///   - timestamp: The timestamp from the verification link.
    ///   - signature: The cryptographic signature.
    case verifyUser(userId: String, timestamp: String, signature: String)

    /// Open registration flow (used by satellite apps to redirect to Juke).
    case register

    /// A custom deep link with arbitrary host, path, and query items.
    case custom(host: String, path: String, queryItems: [String: String])
}

/// Parses deep link URLs into `JukeDeepLink` values.
///
/// Supports both custom URL schemes (e.g., `juke://verify-user`)
/// and universal links (e.g., `https://juke.fm/verify-user`).
///
/// ## Usage
///
/// ```swift
/// let parser = JukeDeepLinkParser(
///     schemes: ["juke", "shotclock"],
///     universalLinkHosts: ["juke.fm", "www.juke.fm"]
/// )
///
/// if let deepLink = parser.parse(url) {
///     switch deepLink {
///     case .verifyUser(let userId, let timestamp, let signature):
///         // Handle verification
///     case .register:
///         // Handle registration
///     case .custom(let host, let path, let params):
///         // Handle custom link
///     }
/// }
/// ```
public struct JukeDeepLinkParser {
    private let schemes: Set<String>
    private let universalLinkHosts: Set<String>

    /// Creates a deep link parser.
    /// - Parameters:
    ///   - schemes: Custom URL schemes to recognize (e.g., ["juke", "shotclock"]).
    ///   - universalLinkHosts: Host names for universal links (e.g., ["juke.fm"]).
    public init(schemes: [String], universalLinkHosts: [String]) {
        self.schemes = Set(schemes.map { $0.lowercased() })
        self.universalLinkHosts = Set(universalLinkHosts.map { $0.lowercased() })
    }

    /// Parses a URL into a deep link.
    /// - Parameter url: The URL to parse.
    /// - Returns: A `JukeDeepLink` if the URL is recognized, or `nil` otherwise.
    public func parse(_ url: URL) -> JukeDeepLink? {
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            return nil
        }

        let scheme = (components.scheme ?? "").lowercased()
        let host = (components.host ?? "").lowercased()
        let path = components.path

        // Check if this is a recognized URL
        let isCustomScheme = schemes.contains(scheme)
        let isUniversalLink = (scheme == "https" || scheme == "http") && universalLinkHosts.contains(host)

        guard isCustomScheme || isUniversalLink else {
            return nil
        }

        // For custom schemes, host is the action; for universal links, path is the action
        let action = isCustomScheme ? host : path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))

        // Parse query parameters
        let params = components.queryParameters

        // Route based on action
        switch action {
        case "verify-user":
            guard let userId = params["user_id"],
                  let timestamp = params["timestamp"],
                  let signature = params["signature"] else {
                return nil
            }
            return .verifyUser(userId: userId, timestamp: timestamp, signature: signature)

        case "register":
            return .register

        default:
            return .custom(host: host, path: path, queryItems: params)
        }
    }
}

// MARK: - URLComponents Extension

public extension URLComponents {
    /// Returns query items as a dictionary.
    var queryParameters: [String: String] {
        var params: [String: String] = [:]
        for item in queryItems ?? [] {
            if let value = item.value {
                params[item.name] = value
            }
        }
        return params
    }
}
