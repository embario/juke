import Foundation

final class AudioActivityThrottle: @unchecked Sendable {
    private let lock = NSLock()
    private var lastEmission = Date.distantPast

    func shouldEmit(at date: Date, minimumInterval: TimeInterval = 0.5) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard date.timeIntervalSince(lastEmission) >= minimumInterval else { return false }
        lastEmission = date
        return true
    }
}
