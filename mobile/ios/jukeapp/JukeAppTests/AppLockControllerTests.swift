import Foundation
import Testing
@testable import JukeApp

@MainActor @Suite(.serialized) struct AppLockControllerTests {
    private func controller(after minutes: Int) -> AppLockController {
        let lock = AppLockController()
        lock.lockAfterMinutes = minutes
        return lock
    }

    @Test func immediateLockEngagesWhenTheAppLeavesTheScreen() {
        let lock = controller(after: 0)
        lock.sceneBecameInactive()
        #expect(lock.isLocked)
    }

    @Test func quickReturnStaysUnlocked() {
        let lock = controller(after: 5)
        lock.sceneBecameInactive()
        lock.sceneBecameActive(isAuthenticated: true)
        #expect(!lock.isLocked)
    }

    @Test func lockNowAlwaysLocks() {
        let lock = controller(after: 15)
        lock.lockNow()
        #expect(lock.isLocked)
    }

    @Test func choiceIsRemembered() {
        _ = controller(after: 15)
        #expect(AppLockController().lockAfterMinutes == 15)
        _ = controller(after: 5)
    }
}
