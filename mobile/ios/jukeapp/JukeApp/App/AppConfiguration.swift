import Foundation

/// Resolves the backend and web sign-in hosts the same way the other Juke iOS apps do:
/// launch environment first, then the `BACKEND_URL` / `FRONTEND_URL` Info.plist keys
/// (filled from the build settings or injected by `scripts/build_and_run_ios.sh` from `.env`),
/// then the Neptune dev server.
struct AppConfiguration: Sendable {
    static let defaultBackendURL = URL(string: "https://neptune.tail647b75.ts.net/")!
    static let shared = AppConfiguration()

    /// Backend origin, always ending in `/` (for example `https://neptune.tail647b75.ts.net/`).
    let backendURL: URL
    /// Web origin that serves `/accounts/login`; defaults to the backend origin.
    let frontendURL: URL

    var apiBaseURL: URL { backendURL.appending(path: "api/v1/") }

    /// The server in use right now: the Settings value when the listener chose one,
    /// otherwise the build/launch value above. Read per request, never cached.
    static var currentBackendURL: URL { JukeServer.baseURL() }
    static var currentAPIBaseURL: URL { JukeServer.apiURL() }
    /// Sign-in page host: the chosen server when set in Settings, else `FRONTEND_URL`.
    static var currentFrontendURL: URL {
        UserDefaults.standard.string(forKey: JukeServer.backendURLKey).flatMap(JukeServer.normalizedBaseURL) ?? shared.frontendURL
    }

    /// Call once at launch so the shared radio/memory clients fall back to `BACKEND_URL`.
    static func installLaunchFallback() {
        JukeServer.fallbackBaseURL = shared.backendURL == defaultBackendURL ? nil : shared.backendURL
    }

    init(environment: [String: String] = ProcessInfo.processInfo.environment, bundle: Bundle = .main) {
        func lookup(_ key: String) -> URL? {
            let candidates = [environment[key], bundle.object(forInfoDictionaryKey: key) as? String]
            for case let raw? in candidates {
                if let url = Self.normalized(raw) { return url }
            }
            return nil
        }
        let backend = lookup("BACKEND_URL") ?? Self.defaultBackendURL
        backendURL = backend
        frontendURL = lookup("FRONTEND_URL") ?? backend
    }

    /// Accepts absolute http(s) URLs, trims whitespace, strips a trailing `/api/v1`, and ensures a trailing slash.
    /// Returns nil for empty strings and unexpanded build settings such as `$(BACKEND_URL)`.
    static func normalized(_ raw: String) -> URL? {
        var value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty, !value.contains("$(") else { return nil }
        while value.hasSuffix("/") { value.removeLast() }
        if value.hasSuffix("/api/v1") { value.removeLast("/api/v1".count) }
        guard let url = URL(string: value + "/"), let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https", url.host() != nil else { return nil }
        return url
    }
}
