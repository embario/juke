import AuthenticationServices
import CryptoKit
import Foundation
import Security
import UIKit

@MainActor
final class JukeAuthService: NSObject, ASWebAuthenticationPresentationContextProviding {
    private let baseURL = URL(string: "https://neptune.tail647b75.ts.net/")!
    private let keychainService = "com.juke.vibe.ios.authentication"
    private var webSession: ASWebAuthenticationSession?

    func signIn(path: String = "accounts/login") async throws -> JukeSession {
        let state = randomString(24)
        let verifier = randomString(32)
        let challenge = base64URL(Data(SHA256.hash(data: Data(verifier.utf8))))
        var components = URLComponents(url: baseURL.appending(path: path), resolvingAgainstBaseURL: false)!
        components.queryItems = [
            .init(name: "client", value: "juke-vibe-ios"), .init(name: "redirect_uri", value: "juke-vibe://auth/callback"),
            .init(name: "state", value: state), .init(name: "code_challenge", value: challenge), .init(name: "code_challenge_method", value: "S256"),
        ]
        let callback = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<URL, Error>) in
            let session = ASWebAuthenticationSession(url: components.url!, callbackURLScheme: "juke-vibe") { url, error in
                if let url { continuation.resume(returning: url) } else { continuation.resume(throwing: error ?? CocoaError(.userCancelled)) }
            }
            session.presentationContextProvider = self
            session.prefersEphemeralWebBrowserSession = false
            webSession = session
            session.start()
        }
        guard let returned = URLComponents(url: callback, resolvingAgainstBaseURL: false)?.queryItems,
              returned.first(where: { $0.name == "state" })?.value == state,
              let code = returned.first(where: { $0.name == "code" })?.value else { throw CocoaError(.validationMissingMandatoryProperty) }
        struct Body: Encodable { let code: String; let code_verifier: String; let redirect_uri: String }
        var request = URLRequest(url: baseURL.appending(path: "api/v1/auth/vibe/exchange"))
        request.httpMethod = "POST"; request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(Body(code: code, code_verifier: verifier, redirect_uri: "juke-vibe://auth/callback"))
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { throw CocoaError(.fileReadUnknown) }
        let value = try JSONDecoder().decode(JukeSession.self, from: data)
        try save(value)
        return value
    }

    func restore() throws -> JukeSession? {
        var query = keychainQuery(); query[kSecReturnData as String] = true; query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(status)) }
        return try JSONDecoder().decode(JukeSession.self, from: data)
    }

    func logout() { SecItemDelete(keychainQuery() as CFDictionary) }
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.flatMap(\.windows).first { $0.isKeyWindow } ?? ASPresentationAnchor()
    }

    private func save(_ value: JukeSession) throws {
        let data = try JSONEncoder().encode(value); let query = keychainQuery(); SecItemDelete(query as CFDictionary)
        var add = query; add[kSecValueData as String] = data; add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(add as CFDictionary, nil); guard status == errSecSuccess else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(status)) }
    }
    private func keychainQuery() -> [String: Any] { [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: keychainService, kSecAttrAccount as String: "current-juke-session-v1"] }
    private func randomString(_ count: Int) -> String { var bytes = [UInt8](repeating: 0, count: count); _ = SecRandomCopyBytes(kSecRandomDefault, count, &bytes); return base64URL(Data(bytes)) }
    private func base64URL(_ data: Data) -> String { data.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
}
