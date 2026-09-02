import CryptoKit
import Foundation
import Security

enum ChatVaultError: Error { case keychain(OSStatus), malformedCiphertext }

actor ChatVault {
    private let service = "com.juke.vibe.shared.chat-vault"
    private let account: String

    init(accountID: String) { account = "account-\(accountID)-chat-key-v1" }

    func seal(_ payload: PrivateChatPayload, messageID: UUID) throws -> Data {
        let box = try AES.GCM.seal(try JSONEncoder().encode(payload), using: loadOrCreateKey(), authenticating: context(messageID))
        guard let combined = box.combined else { throw ChatVaultError.malformedCiphertext }
        return combined
    }

    func open(_ data: Data, messageID: UUID) throws -> PrivateChatPayload {
        let box = try AES.GCM.SealedBox(combined: data)
        let clear = try AES.GCM.open(box, using: loadOrCreateKey(), authenticating: context(messageID))
        return try JSONDecoder().decode(PrivateChatPayload.self, from: clear)
    }

    private func context(_ id: UUID) -> Data { Data("juke-vibe-chat:v1:\(id.uuidString)".utf8) }

    private func loadOrCreateKey() throws -> SymmetricKey {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account, kSecAttrAccessGroup as String: "2WMS6785YD.com.juke.vibe.shared", kSecAttrSynchronizable as String: true, kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecSuccess, let data = result as? Data { return SymmetricKey(data: data) }
        guard status == errSecItemNotFound else { throw ChatVaultError.keychain(status) }
        let data = Data(SymmetricKey(size: .bits256).withUnsafeBytes(Array.init))
        let add: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account, kSecAttrAccessGroup as String: "2WMS6785YD.com.juke.vibe.shared", kSecAttrSynchronizable as String: true, kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock, kSecValueData as String: data]
        let added = SecItemAdd(add as CFDictionary, nil)
        guard added == errSecSuccess else { throw ChatVaultError.keychain(added) }
        return SymmetricKey(data: data)
    }
}

struct PrivateChatPayload: Codable, Sendable {
    let role: String
    let content: String
    let trackIdentity: String?
    let createdAt: Date
}
