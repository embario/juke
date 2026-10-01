import Foundation
import Security

/// Keychain access shared by the Juke Apple apps.
///
/// `accessGroup` is the Juke group every new item is written to. `legacyAccessGroup`
/// is the group used by Juke; the app keeps it in its entitlements only so the
/// iCloud-synchronised chat encryption key can be found and carried over, which keeps
/// encrypted chat history readable after the rename.
enum JukeKeychain {
    static let teamPrefix = "2WMS6785YD"
    static let accessGroup = "\(teamPrefix).com.juke.shared"
    static let legacyAccessGroup = "\(teamPrefix).com.juke.vibe.shared"

    static func genericPasswordQuery(service: String, account: String, accessGroup: String = JukeKeychain.accessGroup) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecAttrAccessGroup as String: accessGroup,
            kSecUseDataProtectionKeychain as String: true,
        ]
    }
}
