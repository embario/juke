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

@Suite struct ReactionEmojiSliderTests {
    @Test func selectingMovesEmojiToTheLeftmostSlotAndPreservesTheRest() {
        var recency = ReactionEmojiRecency(["🔥", "🌙", "☀️"])

        recency.select("☀️")
        #expect(recency.values == ["☀️", "🔥", "🌙"])
        recency.select("🌙")
        #expect(recency.values == ["🌙", "☀️", "🔥"])
    }

    @Test func scrubbingMapsTouchesToClampedSlotsIncludingANeighbor() {
        #expect(ReactionEmojiSliderLogic.slot(at: 0, width: 300, count: 3, spacing: 2) == 0)
        #expect(ReactionEmojiSliderLogic.slot(at: 150, width: 300, count: 3, spacing: 2) == 1)
        #expect(ReactionEmojiSliderLogic.slot(at: 300, width: 300, count: 3, spacing: 2) == 2)
        #expect(ReactionEmojiSliderLogic.slot(at: -20, width: 300, count: 3, spacing: 2) == 0)
        #expect(ReactionEmojiSliderLogic.slot(at: 20, width: 0, count: 3, spacing: 2) == 0)
        let choices = ["🔥", "🌙", "☀️"]
        let start = choices[ReactionEmojiSliderLogic.slot(at: 50, width: 300, count: choices.count, spacing: 2)]
        let release = choices[ReactionEmojiSliderLogic.slot(at: 150, width: 300, count: choices.count, spacing: 2)]
        #expect(start == "🔥")
        #expect(release == "🌙")
    }

    @Test func voiceOverAdjustableActionsChooseTheNextEmojiWithoutWrapping() {
        let choices = ["🔥", "🌙", "☀️"]
        #expect(ReactionEmojiSliderLogic.adjacent(to: "🌙", direction: 1, in: choices) == "☀️")
        #expect(ReactionEmojiSliderLogic.adjacent(to: "🌙", direction: -1, in: choices) == "🔥")
        #expect(ReactionEmojiSliderLogic.adjacent(to: nil, direction: 1, in: choices) == "🔥")
        #expect(ReactionEmojiSliderLogic.adjacent(to: "☀️", direction: 1, in: choices) == nil)
    }

    @Test func recentEmojiOrderPersistsSeparatelyForEachAccount() {
        let suite = "ReactionEmojiSliderTests.\(UUID().uuidString)"
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
