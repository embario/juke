import CoreGraphics
import Foundation
import Testing
@testable import JukeApp

@Suite struct RadioLayoutTests {
    @Test func tallScreensKeepTheFullSleeve() {
        #expect(RadioLayout.sleeveSide(visibleHeight: 900) == RadioLayout.maxSleeve)
    }

    @Test func shortScreensShrinkTheSleeveToFit() {
        let expected: CGFloat = 600 - RadioLayout.fixedContentHeight
        let fitted = RadioLayout.sleeveSide(visibleHeight: 600)
        let shorter = RadioLayout.sleeveSide(visibleHeight: 560)
        #expect(fitted == expected)
        #expect(shorter < fitted)
    }

    @Test func theVinylIsMuchLargerThanBefore() {
        // iPhone 18 Pro (402 wide) and iPhone 17e (390 wide) with plenty of height: the previous maximum was 196.
        #expect(RadioLayout.sleeveSide(visibleHeight: 900, containerWidth: 402) >= 250)
        #expect(RadioLayout.sleeveSide(visibleHeight: 900, containerWidth: 390) >= 240)
    }

    @Test func sleeveAndRecordAlwaysFitBetweenTheMargins() {
        for width in [320, 375, 390, 402, 430, 600] as [CGFloat] {
            let side = RadioLayout.sleeveSide(visibleHeight: 900, containerWidth: width)
            let row = side + RadioLayout.discOffset(side: side)
            #expect(row <= width - 2 * RadioLayout.rowMargin + 1 || side == RadioLayout.minSleeve, "width \(width)")
        }
    }

    @Test func neverShrinksPastTheMinimum() {
        #expect(RadioLayout.sleeveSide(visibleHeight: 300) == RadioLayout.minSleeve)
        #expect(RadioLayout.sleeveSide(visibleHeight: .nan) == RadioLayout.maxSleeve)
    }

    @Test func recordOffsetScalesWithTheSleeve() {
        #expect(RadioLayout.discOffset(side: 240) == 120)
        #expect(RadioLayout.discOffset(side: 140) < RadioLayout.discOffset(side: 240))
    }
}

@Suite struct RadioIssuePresentationTests {
    @Test func dismissingAnIssueSuppressesIdenticalRefreshes() {
        var presentation = RadioIssuePresentation()
        let issue = RadioIssue.unavailable("Juke could not be reached.")

        #expect(presentation.visibleIssue(for: issue) == issue)
        presentation.dismiss(issue)
        for _ in 0..<5 {
            presentation.observe(issue)
            #expect(presentation.visibleIssue(for: issue) == nil)
        }
    }

    @Test func aChangedIssueReplacesTheDismissedIssue() {
        var presentation = RadioIssuePresentation()
        let first = RadioIssue.unavailable("Juke could not be reached.")
        let next = RadioIssue.spotifyNotLinked
        presentation.dismiss(first)

        #expect(presentation.visibleIssue(for: next) == next)
        presentation.observe(next)
        #expect(presentation.dismissedIssue == nil)
        #expect(presentation.visibleIssue(for: first) == first)
    }

    @Test func clearingAnIssueAllowsItToBePresentedAgainLater() {
        var presentation = RadioIssuePresentation()
        let issue = RadioIssue.unavailable("Juke could not be reached.")
        presentation.dismiss(issue)
        presentation.observe(nil)

        #expect(presentation.dismissedIssue == nil)
        #expect(presentation.visibleIssue(for: issue) == issue)
    }
}

@Suite struct ReactionEmojiChooserTests {
    @Test func selectingMovesEmojiToTheLeftmostSlotAndPreservesTheRest() {
        var recency = ReactionEmojiRecency(["🔥", "🌙", "☀️"])

        recency.select("☀️")
        #expect(recency.values == ["☀️", "🔥", "🌙"])
        recency.select("🌙")
        #expect(recency.values == ["🌙", "☀️", "🔥"])
    }

    @Test func chooserCatalogueKeepsItsProductGroupOrder() {
        #expect(ReactionEmojiChooserCatalog.categories.map(\.title) == [
            "Emotions", "Objects", "Activities", "Places", "Nature & Materials",
        ])
        #expect(ReactionEmojiChooserCatalog.orderedEmojis.first == "😌")
        #expect(ReactionEmojiChooserCatalog.orderedEmojis.firstIndex(of: "🚗")! < ReactionEmojiChooserCatalog.orderedEmojis.firstIndex(of: "🏡")!)
        #expect(ReactionEmojiChooserCatalog.orderedEmojis.firstIndex(of: "🏡")! < ReactionEmojiChooserCatalog.orderedEmojis.firstIndex(of: "🪨")!)
        #expect(Set(ReactionEmojiChooserCatalog.orderedEmojis).count == ReactionEmojiChooserCatalog.orderedEmojis.count)
    }

    @Test func compactRowShowsRecentEmojisFirstAndAddsCurrentSelections() {
        #expect(ReactionEmojiChooserCatalog.recentChoices(
            recent: ["☕", "😌", "☕"],
            selected: ["🥹", "mellow", "😌"],
            limit: 4
        ) == ["☕", "😌", "🥹"])
        #expect(ReactionEmojiChooserCatalog.recentChoices(recent: ["☕", "😌"], selected: [], limit: 1) == ["☕"])
    }

    @Test func customEmojiAppearAfterTheOrderedCatalogueButWordsDoNot() {
        let groups = ReactionEmojiChooserCatalog.categories(includingCustom: ["💚", "mellow", "🌸"])
        #expect(groups.map(\.title).last == "Your emojis")
        #expect(groups.last?.emojis == ["💚"])
    }

    @Test func recentEmojiOrderPersistsSeparatelyForEachAccount() {
        let suite = "ReactionEmojiChooserTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let one = RadioPreferences(defaults: defaults, accountID: "one")
        let two = RadioPreferences(defaults: defaults, accountID: "two")

        one.recentEmojiReactions = ["🌙", "🔥"]
        #expect(RadioPreferences(defaults: defaults, accountID: "one").recentEmojiReactions == ["🌙", "🔥"])
        #expect(two.recentEmojiReactions.isEmpty)
    }
}

@Suite struct TunerDrawerGestureTests {
    private typealias Gesture = TunerDrawerGesture

    @Test func draggingUpOpensAsTheFingerMoves() {
        #expect(Gesture.progress(expanded: false, translation: -50, travel: 100) == 0.5)
        #expect(Gesture.progress(expanded: false, translation: -500, travel: 100) == 1)
        #expect(Gesture.progress(expanded: false, translation: 40, travel: 100) == 0, "pulling a closed drawer down does nothing")
    }

    @Test func draggingDownClosesAsTheFingerMoves() {
        #expect(Gesture.progress(expanded: true, translation: 25, travel: 100) == 0.75)
        #expect(Gesture.progress(expanded: true, translation: -80, travel: 100) == 1)
        #expect(Gesture.progress(expanded: true, translation: 400, travel: 100) == 0)
    }

    @Test func noTravelDoesNotDivideByZero() {
        #expect(Gesture.progress(expanded: false, translation: -80, travel: 0) == 0)
        #expect(Gesture.progress(expanded: true, translation: 80, travel: 0) == 1)
    }

    @Test func aDragLetGoEarlyGoesBack() {
        #expect(!Gesture.settles(expanded: false, translation: -30, velocity: 0, travel: 100), "cancelled before the commit point")
        #expect(Gesture.settles(expanded: false, translation: -50, velocity: 0, travel: 100))
        #expect(Gesture.settles(expanded: true, translation: 30, velocity: 0, travel: 100), "cancelled: still open")
        #expect(!Gesture.settles(expanded: true, translation: 70, velocity: 0, travel: 100))
    }

    @Test func aFlickDecidesByDirection() {
        #expect(Gesture.settles(expanded: false, translation: -10, velocity: -900, travel: 100))
        #expect(!Gesture.settles(expanded: true, translation: 10, velocity: 900, travel: 100))
        #expect(!Gesture.settles(expanded: false, translation: -90, velocity: 900, travel: 100), "a downward flick wins over a long upward drag")
    }
}
