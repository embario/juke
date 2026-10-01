import Foundation
import LocalAuthentication
import Observation

@MainActor
@Observable
final class AppLockController {
    var isLocked = false
    var unlockError: String?
    var onLock: (() -> Void)?
    var lockAfterMinutes: Int {
        didSet { UserDefaults.standard.set(lockAfterMinutes, forKey: "vibe.lockAfterMinutes") }
    }

    private var becameInactiveAt: Date?
    @ObservationIgnored private var scheduledLock: Task<Void, Never>?

    init() {
        lockAfterMinutes = UserDefaults.standard.object(forKey: "vibe.lockAfterMinutes") as? Int ?? 5
    }

    func sceneBecameInactive() {
        guard becameInactiveAt == nil else { return }
        becameInactiveAt = .now
        scheduledLock?.cancel()
        let delay = lockAfterMinutes
        if delay == 0 {
            lockNow()
        } else {
            scheduledLock = Task { @MainActor [weak self] in
                try? await Task.sleep(for: .seconds(delay * 60))
                guard !Task.isCancelled else { return }
                self?.lockNow()
            }
        }
    }

    func sceneBecameActive(isAuthenticated: Bool) {
        scheduledLock?.cancel()
        scheduledLock = nil
        defer { becameInactiveAt = nil }
        guard isAuthenticated, let becameInactiveAt else { return }
        if Date().timeIntervalSince(becameInactiveAt) >= Double(lockAfterMinutes * 60) {
            lockNow()
        }
    }

    func lockNow() {
        isLocked = true
        onLock?()
    }

    func unlock() async {
        let context = LAContext()
        context.localizedCancelTitle = "Keep Locked"
        do {
            let success = try await context.evaluatePolicy(
                .deviceOwnerAuthentication,
                localizedReason: "Unlock your private Juke conversations"
            )
            if success {
                isLocked = false
                unlockError = nil
                becameInactiveAt = nil
            }
        } catch {
            unlockError = error.localizedDescription
        }
    }
}
