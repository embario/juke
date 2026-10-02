import Foundation
import Security

/// Keychain access shared by the Juke Apple apps.
///
/// The group keeps its Juke Vibe name on purpose: the chat encryption key is an
/// iCloud-synchronised item in this group, shared with Juke for iPhone. Renaming
/// the group (or the chat-vault service) would orphan that key and make the
/// encrypted chat records stored on Juke unreadable.
enum JukeKeychain {
    static let accessGroup = "2WMS6785YD.com.juke.vibe.shared"

    static func genericPasswordQuery(service: String, account: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecAttrAccessGroup as String: accessGroup,
            kSecUseDataProtectionKeychain as String: true,
        ]
    }
}
