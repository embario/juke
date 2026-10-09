import CryptoKit
import Foundation

enum MessageSafetyNotice {
    static let recordKind = "messageSafetyNotice"
    static let message = "This message is safe on this iPhone; encrypted sync will retry when Neptune is reachable."
    private static let keyPrefix = "vibe.messageSafetyNoticeSeen."

    static func hasBeenShown(for accountID: String, defaults: UserDefaults = .standard) -> Bool {
        defaults.bool(forKey: keyPrefix + accountID)
    }

    @discardableResult
    static func markShown(for accountID: String, defaults: UserDefaults = .standard) -> Bool {
        guard !hasBeenShown(for: accountID, defaults: defaults) else { return false }
        defaults.set(true, forKey: keyPrefix + accountID)
        return true
    }

    /// Stable across devices so retries update the same encrypted sync record.
    static func recordID(for accountID: String) -> UUID {
        let digest = SHA256.hash(data: Data("juke.message-safety-notice.v1:\(accountID)".utf8))
        let hex = digest.prefix(16).map { String(format: "%02x", $0) }.joined()
        let value = "\(hex.prefix(8))-\(hex.dropFirst(8).prefix(4))-\(hex.dropFirst(12).prefix(4))-\(hex.dropFirst(16).prefix(4))-\(hex.dropFirst(20).prefix(12))"
        return UUID(uuidString: value)!
    }
}
