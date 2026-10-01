import CryptoKit
import Foundation
import Security

enum ChatVaultError: Error { case keychain(OSStatus), malformedCiphertext }

actor ChatVault {
    // Shared with Juke for iPhone through iCloud Keychain. Never rename.
    private let service = "com.juke.vibe.shared.chat-vault"
    private let account: String
    private var cachedKey: SymmetricKey?

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

    // This authenticated-data label predates the rename and is bound into every
    // stored ciphertext, so it must never change.
    private func context(_ id: UUID) -> Data { Data("juke-vibe-chat:v1:\(id.uuidString)".utf8) }

    private func loadOrCreateKey() throws -> SymmetricKey {
        if ProcessInfo.processInfo.arguments.contains("--uitesting") {
            return SymmetricKey(data: Data(repeating: 0x4A, count: 32))
        }
        if let cachedKey { return cachedKey }
        var query = JukeKeychain.genericPasswordQuery(service: service, account: account)
        query[kSecAttrSynchronizable as String] = true
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecSuccess, let data = result as? Data {
            let key = SymmetricKey(data: data)
            cachedKey = key
            return key
        }
        guard status == errSecItemNotFound else { throw ChatVaultError.keychain(status) }
        let data = Data(SymmetricKey(size: .bits256).withUnsafeBytes(Array.init))
        var add = JukeKeychain.genericPasswordQuery(service: service, account: account)
        add[kSecAttrSynchronizable as String] = true
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        add[kSecValueData as String] = data
        let added = SecItemAdd(add as CFDictionary, nil)
        guard added == errSecSuccess else { throw ChatVaultError.keychain(added) }
        let key = SymmetricKey(data: data)
        cachedKey = key
        return key
    }
}

struct PrivateChatPayload: Codable, Sendable {
    let role: String
    let content: String
    let trackIdentity: String?
    let createdAt: Date
}
