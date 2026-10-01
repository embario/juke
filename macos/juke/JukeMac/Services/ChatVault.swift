import CryptoKit
import Foundation
import Security

enum ChatVaultError: Error { case keychain(OSStatus), malformedCiphertext }

actor ChatVault {
    private let service = "com.juke.shared.chat-vault"
    static let legacyService = "com.juke.vibe.shared.chat-vault"
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

    // The authenticated-data label predates the rename. It is part of every
    // stored ciphertext, so it must not change.
    // This authenticated-data label predates the rename and is bound into every
    // stored ciphertext, so it must never change.
    private func context(_ id: UUID) -> Data { Data("juke-vibe-chat:v1:\(id.uuidString)".utf8) }

    private func loadOrCreateKey() throws -> SymmetricKey {
        if ProcessInfo.processInfo.arguments.contains("--uitesting") {
            return SymmetricKey(data: Data(repeating: 0x4A, count: 32))
        }
        if let cachedKey { return cachedKey }
        if let data = try readKey(service: service, accessGroup: JukeKeychain.accessGroup) {
            return cache(data)
        }
        // Juke stored the key under its own group; adopt it so existing
        // encrypted chat records (local and on Juke) stay readable.
        if let legacy = try? readKey(service: Self.legacyService, accessGroup: JukeKeychain.legacyAccessGroup) {
            try? addKey(legacy)
            return cache(legacy)
        }
        let data = Data(SymmetricKey(size: .bits256).withUnsafeBytes(Array.init))
        try addKey(data)
        return cache(data)
    }

    private func cache(_ data: Data) -> SymmetricKey {
        let key = SymmetricKey(data: data)
        cachedKey = key
        return key
    }

    private func readKey(service: String, accessGroup: String) throws -> Data? {
        var query = JukeKeychain.genericPasswordQuery(service: service, account: account, accessGroup: accessGroup)
        query[kSecAttrSynchronizable as String] = true
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else { throw ChatVaultError.keychain(status) }
        return data
    }

    private func addKey(_ data: Data) throws {
        var add = JukeKeychain.genericPasswordQuery(service: service, account: account)
        add[kSecAttrSynchronizable as String] = true
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        add[kSecValueData as String] = data
        let added = SecItemAdd(add as CFDictionary, nil)
        guard added == errSecSuccess else { throw ChatVaultError.keychain(added) }
    }
}

struct PrivateChatPayload: Codable, Sendable {
    let role: String
    let content: String
    let trackIdentity: String?
    let createdAt: Date
}
