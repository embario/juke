import CryptoKit
import Foundation
import Security

actor ChatVault {
    let accountID: String
    // The vault key, its keychain group and the AEAD context keep their original "vibe" names on purpose:
    // the key syncs through iCloud Keychain between the iOS and macOS apps, and renaming any of them would
    // make chat records already stored on the backend undecryptable.
    private let service = "com.juke.vibe.shared.chat-vault"

    init(accountID: String) { self.accountID = accountID }

    func seal(_ payload: PrivateChatPayload, id: UUID) throws -> Data {
        let box = try AES.GCM.seal(try JSONEncoder().encode(payload), using: loadOrCreate(), authenticating: context(id))
        guard let combined = box.combined else { throw CocoaError(.coderInvalidValue) }
        return combined
    }

    func open(_ data: Data, id: UUID) throws -> PrivateChatPayload {
        let clear = try AES.GCM.open(try AES.GCM.SealedBox(combined: data), using: loadOrCreate(), authenticating: context(id))
        return try JSONDecoder().decode(PrivateChatPayload.self, from: clear)
    }

    private func context(_ id: UUID) -> Data { Data("juke-vibe-chat:v1:\(id.uuidString)".utf8) }
    private func loadOrCreate() throws -> SymmetricKey {
        let account = "account-\(accountID)-chat-key-v1"
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account, kSecAttrAccessGroup as String: "2WMS6785YD.com.juke.vibe.shared", kSecAttrSynchronizable as String: true, kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecSuccess, let data = result as? Data { return SymmetricKey(data: data) }
        guard status == errSecItemNotFound else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(status)) }
        let data = Data(SymmetricKey(size: .bits256).withUnsafeBytes(Array.init))
        let add: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account, kSecAttrAccessGroup as String: "2WMS6785YD.com.juke.vibe.shared", kSecAttrSynchronizable as String: true, kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock, kSecValueData as String: data]
        let added = SecItemAdd(add as CFDictionary, nil)
        guard added == errSecSuccess else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(added)) }
        return SymmetricKey(data: data)
    }
}

struct PrivateChatPayload: Codable, Sendable {
    let role: String
    let content: String
    let trackIdentity: String?
    let createdAt: Date
}
