import Foundation

/// Which memory the Memories card shows, and which way the last flip went.
///
/// One memory at a time, like the design's ‹ n of N ›. Flipping wraps around
/// at both ends. When the list changes (refresh, search, a new memory) the
/// current memory stays put if it is still there; otherwise the card shows
/// the memory now at the same position.
struct MemoryBrowser: Equatable, Sendable {
    enum Direction: Equatable, Sendable { case forward, backward }

    private(set) var ids: [UUID] = []
    private(set) var currentID: UUID?
    private(set) var direction: Direction = .forward

    var index: Int? { currentID.flatMap { ids.firstIndex(of: $0) } }
    var count: Int { ids.count }
    var canFlip: Bool { ids.count > 1 }

    /// "2 of 5", or empty when there is nothing to show.
    var positionLabel: String {
        guard let index else { return "" }
        return "\(index + 1) of \(ids.count)"
    }

    mutating func update(ids newIDs: [UUID]) {
        let previousIndex = index
        ids = newIDs
        if let pendingID, newIDs.contains(pendingID) {
            currentID = pendingID
            self.pendingID = nil
            return
        }
        if let currentID, newIDs.contains(currentID) { return }
        guard !newIDs.isEmpty else { currentID = nil; return }
        currentID = newIDs[min(previousIndex ?? 0, newIDs.count - 1)]
    }

    mutating func next() { step(by: 1) }
    mutating func previous() { step(by: -1) }

    /// Shows a specific memory. Unknown IDs are kept so a memory that is still
    /// being saved can be shown as soon as the list includes it.
    mutating func select(_ id: UUID) {
        if let from = index, let to = ids.firstIndex(of: id) {
            direction = to >= from ? .forward : .backward
        } else {
            direction = .forward
        }
        currentID = id
        pendingID = ids.contains(id) ? nil : id
    }

    /// A selected memory the list does not hold yet (for example one just
    /// saved while a search hid it); shown as soon as it appears.
    private(set) var pendingID: UUID?

    private mutating func step(by offset: Int) {
        guard !ids.isEmpty else { return }
        let start = index ?? (offset > 0 ? -1 : 0)
        let next = ((start + offset) % ids.count + ids.count) % ids.count
        direction = offset > 0 ? .forward : .backward
        currentID = ids[next]
        pendingID = nil
    }
}
