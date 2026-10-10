import Foundation
import Testing
@testable import JukeApp

@Suite struct MemoryDeckTests {
    private func memories(_ count: Int) -> [MusicMemory] {
        (0..<count).map { index in
            MusicMemory(id: UUID(), title: "Memory \(index)", text: "", occurredAt: Date(timeIntervalSince1970: Double(index) * 86_400), createdAt: Date(),
                        place: "", people: [], songs: [], media: [], tags: [], classification: .unavailable)
        }
    }

    @Test func aDeckHoldsEveryMemoryExactlyOnce() {
        let all = memories(12)
        let deck = MemoryDeck.shuffled(all, seed: 1)
        #expect(deck.count == 12)
        #expect(Set(deck.order) == Set(all.map(\.id)))
        #expect(deck.position == 1)
    }

    @Test func theSameSeedDealsTheSameOrderAndOtherSeedsDoNot() {
        let all = memories(12)
        #expect(MemoryDeck.shuffled(all, seed: 5) == MemoryDeck.shuffled(all, seed: 5))
        let orders = Set((1...6).map { MemoryDeck.shuffled(all, seed: UInt64($0)).order })
        #expect(orders.count > 1, "different seeds must not all deal the same order")
        #expect(MemoryDeck.shuffled(all, seed: 5).order != all.map(\.id), "a shuffle is not the saved order")
    }

    @Test func emptyAndSingleDecksAreSafe() {
        var empty = MemoryDeck.shuffled([], seed: 1)
        #expect(empty.isEmpty && empty.top == nil && empty.position == 0 && empty.visible().isEmpty)
        empty.advance(); empty.retreat()
        #expect(empty.isEmpty)
        let one = memories(1)
        var single = MemoryDeck.shuffled(one, seed: 1)
        single.advance(); single.retreat()
        #expect(single.top == one[0].id && single.position == 1, "one card stays put")
        single.reshuffle(one, seed: 9)
        #expect(single.top == one[0].id)
    }

    @Test func advancingSendsTheTopCardToTheBottomAndRetreatingBringsItBack() {
        let all = memories(4)
        var deck = MemoryDeck.shuffled(all, seed: 3)
        let start = deck.order
        deck.advance()
        #expect(deck.order == Array(start.dropFirst()) + [start[0]])
        #expect(deck.position == 2)
        deck.retreat()
        #expect(deck.order == start && deck.position == 1)
        for _ in 0..<4 { deck.advance() }
        #expect(deck.order == start && deck.position == 1, "a full lap returns to the first card")
        deck.retreat()
        #expect(deck.position == 4 && deck.top == start.last)
    }

    @Test func visibleIsTheTopFewCards() {
        let deck = MemoryDeck.shuffled(memories(5), seed: 2)
        #expect(deck.visible(limit: 3) == Array(deck.order.prefix(3)))
        #expect(MemoryDeck.shuffled(memories(2), seed: 2).visible(limit: 3).count == 2)
    }

    @Test func reshufflingNeverLeavesTheSameCardOnTop() {
        let all = memories(6)
        var deck = MemoryDeck.shuffled(all, seed: 1)
        for seed in 1...40 as ClosedRange<UInt64> {
            let before = deck.top
            deck.reshuffle(all, seed: seed)
            #expect(deck.top != before)
            #expect(Set(deck.order) == Set(all.map(\.id)) && deck.position == 1)
        }
    }

    @Test func deletingAMemoryRemovesItWithoutReshufflingTheRest() {
        let all = memories(5)
        var deck = MemoryDeck.shuffled(all, seed: 4)
        deck.advance()
        let before = deck.order
        let gone = before[2]
        deck.sync(with: all.filter { $0.id != gone }, seed: 1)
        #expect(deck.order == before.filter { $0 != gone })
        #expect(deck.count == 4)
        #expect(deck.position >= 1 && deck.position <= deck.count)
    }

    @Test func deletingTheLastMemoryEmptiesTheDeck() {
        let all = memories(1)
        var deck = MemoryDeck.shuffled(all, seed: 1)
        deck.sync(with: [], seed: 1)
        #expect(deck.isEmpty && deck.position == 0)
    }

    @Test func newMemoriesAreDealtOnTopOfTheDeck() {
        let all = memories(4)
        var deck = MemoryDeck.shuffled(all, seed: 4)
        deck.advance(); deck.advance()
        let before = deck.order
        let added = memories(1)[0]
        deck.sync(with: all + [added], seed: 2)
        #expect(deck.top == added.id)
        #expect(Array(deck.order.dropFirst()) == before)
        #expect(deck.position == 1)
    }

    @Test func firstSyncDealsAShuffledDeckFromTheStore() {
        let all = memories(8)
        var deck = MemoryDeck()
        deck.sync(with: all, seed: 11)
        #expect(Set(deck.order) == Set(all.map(\.id)) && deck.count == 8)
        deck.sync(with: all, seed: 99)
        #expect(deck.count == 8, "a refresh with the same memories changes nothing")
    }

    @Test func seededGeneratorIsDeterministic() {
        var a = SeededGenerator(seed: 42), b = SeededGenerator(seed: 42), c = SeededGenerator(seed: 43)
        #expect((0..<5).map { _ in a.next() } == (0..<5).map { _ in b.next() })
        #expect(a.next() != c.next())
    }
}

@Suite struct MemoryDeckStyleTests {
    private func memory(title: String = "Beach", place: String = "", songs: [MemorySong] = []) -> MusicMemory {
        MusicMemory(id: UUID(), title: title, text: "", occurredAt: Date(timeIntervalSince1970: 1_700_000_000), createdAt: Date(),
                    place: place, people: [], songs: songs, media: [], tags: [], classification: .unavailable)
    }

    @Test func tiltStaysSmallAndStablePerMemory() {
        for _ in 0..<200 {
            let id = UUID()
            #expect((-3...3).contains(MemoryDeckStyle.tilt(for: id)))
            #expect(MemoryDeckStyle.tilt(for: id) == MemoryDeckStyle.tilt(for: id))
        }
    }

    @Test func aSwipeAdvancesOnDistanceOrFlick() {
        #expect(!MemoryDeckStyle.shouldAdvance(translation: 40, predicted: 120))
        #expect(MemoryDeckStyle.shouldAdvance(translation: -140, predicted: -150))
        #expect(MemoryDeckStyle.shouldAdvance(translation: 30, predicted: 400), "a quick flick counts")
    }

    @Test func onlyMostlySidewaysDragsMoveTheCard() {
        #expect(MemoryDeckStyle.isSideways(CGSize(width: 90, height: 20)))
        #expect(!MemoryDeckStyle.isSideways(CGSize(width: 20, height: 90)), "a vertical drag is a page scroll")
        #expect(!MemoryDeckStyle.isSideways(CGSize(width: 50, height: 50)), "a diagonal drag is left to the page")
        #expect(!MemoryDeckStyle.isSideways(.zero))
    }

    @Test func theDeckReservesRoomForThePlayerIsland() {
        #expect(MemoryDeckStyle.islandInset >= 96, "the island (~60pt) plus the tab bar (~64pt) overlap the page bottom")
    }

    @Test func subtitleAndAccessibilityLabelNameTheMemory() {
        let song = MemorySong(title: "So What", artist: "Miles Davis", provider: "spotify", providerID: nil)
        let plain = memory(), placed = memory(place: "Lake George", songs: [song])
        #expect(!MemoryDeckStyle.subtitle(plain).contains("·"))
        #expect(MemoryDeckStyle.subtitle(placed).hasSuffix("· Lake George"))
        #expect(MemoryDeckStyle.accessibilityLabel(placed).hasPrefix("Beach, "))
        #expect(MemoryDeckStyle.accessibilityLabel(placed).hasSuffix("So What by Miles Davis"))
    }
}
