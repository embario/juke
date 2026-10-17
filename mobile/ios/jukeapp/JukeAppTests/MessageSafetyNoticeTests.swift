import Foundation
import Testing
@testable import JukeApp

@Suite struct MessageSafetyNoticeTests {
    @Test func shownStatePersistsByAccountAndDoesNotLeakToAnotherAccount() {
        let suiteName = "message-safety-notice-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }

        #expect(!MessageSafetyNotice.hasBeenShown(for: "account-a", defaults: defaults))
        #expect(MessageSafetyNotice.markShown(for: "account-a", defaults: defaults))
        #expect(MessageSafetyNotice.hasBeenShown(for: "account-a", defaults: defaults))
        #expect(!MessageSafetyNotice.markShown(for: "account-a", defaults: defaults))
        #expect(!MessageSafetyNotice.hasBeenShown(for: "account-b", defaults: defaults))
    }

    @Test func acknowledgementRecordIDIsStableAndAccountScoped() {
        let first = MessageSafetyNotice.recordID(for: "account-a")
        #expect(MessageSafetyNotice.recordID(for: "account-a") == first)
        #expect(MessageSafetyNotice.recordID(for: "account-b") != first)
    }
}
