import Foundation
import Security

enum VibeKeychain {
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
