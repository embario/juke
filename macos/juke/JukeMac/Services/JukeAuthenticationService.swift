import AppKit
import CryptoKit
import Foundation
import Security

enum JukeAuthDestination {
    case login, createAccount, forgotPassword

    var path: String {
        switch self {
        case .login: "accounts/login"
        case .createAccount: "accounts/signup"
        case .forgotPassword: "accounts/password/reset"
        }
    }
}

enum JukeAuthError: LocalizedError {
    case invalidCallback, exchangeUnavailable, keychain(OSStatus)

    var errorDescription: String? {
        switch self {
        case .invalidCallback: "Juke returned an invalid sign-in response."
        case .exchangeUnavailable: "Juke sign-in could not be completed. Check your connection to Neptune."
        case .keychain: "The secure account session could not be accessed."
        }
    }
}

actor JukeAuthenticationService {
    private struct PendingAttempt { let state: String; let verifier: String }
    private struct SpotifyConnectTicketResponse: Decodable {
        let connectURL: URL

        enum CodingKeys: String, CodingKey {
            case connectURL = "connect_url"
        }
    }

    /// OAuth-like client registered in the backend's `VIBE_OAUTH_CLIENTS`.
    nonisolated static let clientID = "juke-app-mac"
    nonisolated static let callbackScheme = "juke-app"
    nonisolated static let redirectURI = "juke-app://auth/callback"

    private let service = "com.juke.mac.authentication"
    private let account = "current-juke-session-v1"
    private var baseURL: URL { JukeServer.baseURL() }
    private var pendingAttempt: PendingAttempt?
    private let session: URLSession

    nonisolated static func spotifyConnectTicketRequest(token: String, baseURL: URL = JukeServer.baseURL()) throws -> URLRequest {
        let url = baseURL.appending(path: "api/v1/auth/spotify/connect-ticket/")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "return_to": baseURL.absoluteString,
        ])
        return request
    }

    func spotifyConnectionURL(token: String) async throws -> URL {
        let request = try Self.spotifyConnectTicketRequest(token: token)
        let (data, response) = try await session.data(for: request)
        guard data.count <= 1_048_576,
              let http = response as? HTTPURLResponse,
              http.statusCode == 201,
              let result = try? JSONDecoder().decode(SpotifyConnectTicketResponse.self, from: data)
        else { throw JukeAuthError.exchangeUnavailable }
        return result.connectURL
    }

    init() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.timeoutIntervalForRequest = 15
        session = URLSession(configuration: configuration)
    }

    func restoreSession() throws -> JukeSession? {
        var query = keychainQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else { throw JukeAuthError.keychain(status) }
        return try JSONDecoder().decode(JukeSession.self, from: data)
    }

    func browserURL(for destination: JukeAuthDestination) -> URL {
        let state = randomURLSafeString(byteCount: 24)
        let verifier = randomURLSafeString(byteCount: 32)
        let challenge = Self.base64URL(Data(SHA256.hash(data: Data(verifier.utf8))))
        pendingAttempt = PendingAttempt(state: state, verifier: verifier)
        var components = URLComponents(url: baseURL.appending(path: destination.path), resolvingAgainstBaseURL: false)!
        components.queryItems = [
            URLQueryItem(name: "client", value: Self.clientID),
            URLQueryItem(name: "redirect_uri", value: Self.redirectURI),
            URLQueryItem(name: "state", value: state),
            URLQueryItem(name: "code_challenge", value: challenge),
            URLQueryItem(name: "code_challenge_method", value: "S256"),
        ]
        return components.url!
    }

    func complete(callbackURL: URL) async throws -> JukeSession {
        guard callbackURL.scheme == Self.callbackScheme, callbackURL.host == "auth", callbackURL.path == "/callback",
              let items = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false)?.queryItems,
              let code = items.first(where: { $0.name == "code" })?.value,
              let returnedState = items.first(where: { $0.name == "state" })?.value,
              let pendingAttempt, returnedState == pendingAttempt.state else { throw JukeAuthError.invalidCallback }
        self.pendingAttempt = nil
        var request = URLRequest(url: baseURL.appending(path: "api/v1/auth/vibe/exchange"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode([
            "code": code,
            "code_verifier": pendingAttempt.verifier,
            "redirect_uri": Self.redirectURI,
        ])
        let (data, response) = try await session.data(for: request)
        guard data.count <= 1_048_576,
              let http = response as? HTTPURLResponse, http.statusCode == 200 else { throw JukeAuthError.exchangeUnavailable }
        let value = try JSONDecoder().decode(JukeSession.self, from: data)
        try save(value)
        return value
    }

    func logout() throws {
        let query = keychainQuery()
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw JukeAuthError.keychain(status) }
    }

    private func save(_ value: JukeSession) throws {
        let data = try JSONEncoder().encode(value)
        let query = keychainQuery()
        SecItemDelete(query as CFDictionary)
        var add = query
        add[kSecValueData as String] = data
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(add as CFDictionary, nil)
        guard status == errSecSuccess else { throw JukeAuthError.keychain(status) }
    }

    private func keychainQuery() -> [String: Any] {
        JukeKeychain.genericPasswordQuery(service: service, account: account)
    }

    private func randomURLSafeString(byteCount: Int) -> String {
        var bytes = [UInt8](repeating: 0, count: byteCount)
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else {
            return UUID().uuidString.replacingOccurrences(of: "-", with: "") + UUID().uuidString.replacingOccurrences(of: "-", with: "")
        }
        return Self.base64URL(Data(bytes))
    }

    private static func base64URL(_ data: Data) -> String {
        data.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    }
}
