import Foundation

/// A small seedable generator, so a shuffle can be reproduced in tests and UI checks.
struct SeededGenerator: RandomNumberGenerator {
    private var state: UInt64
    init(seed: UInt64) { state = seed }

    mutating func next() -> UInt64 {
        state &+= 0x9E37_79B9_7F4A_7C15
        var value = state
        value = (value ^ (value >> 30)) &* 0xBF58_476D_1CE4_E5B9
        value = (value ^ (value >> 27)) &* 0x94D0_49BB_1331_11EB
        return value ^ (value >> 31)
    }
}

/// The order memories are dealt in on the Memories landing: a shuffled deck.
/// Swiping the top card sends it to the bottom; the deck survives refreshes and deletes without reshuffling.
struct MemoryDeck: Equatable {
    private(set) var order: [UUID] = []
    /// How many cards have been moved on from the first one dealt, for "3 of 12".
    private(set) var topIndex = 0

    var count: Int { order.count }
    var isEmpty: Bool { order.isEmpty }
    var top: UUID? { order.first }
    var position: Int { isEmpty ? 0 : topIndex + 1 }

    /// The cards to draw, top first.
    func visible(limit: Int = 3) -> [UUID] { Array(order.prefix(limit)) }

    static func shuffled(_ memories: [MusicMemory], seed: UInt64) -> MemoryDeck {
        var generator = SeededGenerator(seed: seed)
        var deck = MemoryDeck()
        deck.order = memories.map(\.id).shuffled(using: &generator)
        return deck
    }

    /// Follows the store: deleted memories leave the deck, new ones (saved or synced) are dealt on top.
    mutating func sync(with memories: [MusicMemory], seed: UInt64) {
        let live = Set(memories.map(\.id))
        let known = Set(order)
        let kept = order.filter { live.contains($0) }
        let added = memories.filter { !known.contains($0.id) }
        let fresh = MemoryDeck.shuffled(added, seed: seed).order
        if kept.isEmpty { order = fresh; topIndex = 0; return }
        order = fresh + kept
        topIndex = fresh.isEmpty ? min(topIndex, order.count - 1) : 0
    }

    /// Moves the top card to the bottom.
    mutating func advance() {
        guard order.count > 1 else { return }
        order.append(order.removeFirst())
        topIndex = (topIndex + 1) % order.count
    }

    /// Brings the bottom card back to the top.
    mutating func retreat() {
        guard order.count > 1 else { return }
        order.insert(order.removeLast(), at: 0)
        topIndex = (topIndex + order.count - 1) % order.count
    }

    /// A fresh shuffle that never leaves the same card on top.
    mutating func reshuffle(_ memories: [MusicMemory], seed: UInt64) {
        let previousTop = top
        var next = MemoryDeck.shuffled(memories, seed: seed)
        if next.count > 1, next.top == previousTop { next.order.append(next.order.removeFirst()) }
        self = next
    }
}
