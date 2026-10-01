import Foundation

/// The one place that knows which Juke backend the app talks to.
///
/// The base URL is a user setting (`JukeSettings.backendURL`). Every client
/// resolves it per request through this type, so a change in Settings applies
/// to the next request without restarting the app. Reading `UserDefaults` is
/// thread-safe, which keeps this usable from actors and nonisolated code.
enum JukeServer {
    static let defaultBaseURL = URL(string: "https://neptune.tail647b75.ts.net/")!
    static let backendURLKey = "juke.settings.backendURL"

    /// The configured backend root, always ending in `/`.
    static func baseURL(defaults: UserDefaults = .standard) -> URL {
        defaults.string(forKey: backendURLKey).flatMap(normalizedBaseURL) ?? defaultBaseURL
    }

    /// `<base>/api/v1/`, the root of every REST endpoint.
    static func apiURL(defaults: UserDefaults = .standard) -> URL {
        baseURL(defaults: defaults).appending(path: "api/v1/")
    }

    /// Validates and normalises user input for the backend URL.
    ///
    /// HTTPS is required, except for loopback hosts used during local
    /// development. A trailing `api/v1` is removed, because clients append it. Query strings, fragments and credentials are rejected so a
    /// token is never sent somewhere unexpected.
    static func normalizedBaseURL(_ text: String) -> URL? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard var components = URLComponents(string: trimmed),
              let scheme = components.scheme?.lowercased(),
              let host = components.host?.lowercased(), !host.isEmpty,
              components.query == nil, components.fragment == nil,
              components.user == nil, components.password == nil
        else { return nil }
        let loopback = host == "localhost" || host == "127.0.0.1" || host == "::1" || host == "[::1]"
        guard scheme == "https" || (scheme == "http" && loopback) else { return nil }
        components.scheme = scheme
        components.host = host
        // People often paste the API root; the base is the server root.
        var path = components.path
        while path.hasSuffix("/") { path.removeLast() }
        if path.lowercased().hasSuffix("/api/v1") { path.removeLast("/api/v1".count) }
        components.path = path + "/"
        return components.url
    }
}
