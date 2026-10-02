import Foundation
import XCTest
@testable import Juke

// MARK: - Crate transforms and stepping

final class CrateLayoutTests: XCTestCase {
    func testSideToSideMatchesThePrototypeCoverflow() {
        let front = CrateLayout.transform(index: 3, position: 3, mode: .sideToSide)
        XCTAssertEqual(front, CrateSleeveTransform(x: 0, y: 0, rotationX: 0, rotationY: 0, scale: 1, opacity: 1, brightness: 1, zIndex: 100))

        let right = CrateLayout.transform(index: 4, position: 3, mode: .sideToSide)
        XCTAssertEqual(right.x, 184, accuracy: 0.001)          // 1 × 64 + 120
        XCTAssertEqual(right.rotationY, -60, accuracy: 0.001)
        XCTAssertEqual(right.scale, 0.9, accuracy: 0.001)
        XCTAssertEqual(right.brightness, 0.94, accuracy: 0.001)
        XCTAssertEqual(right.zIndex, 90)

        let halfLeft = CrateLayout.transform(index: 2, position: 2.5, mode: .sideToSide)
        XCTAssertEqual(halfLeft.x, -92, accuracy: 0.001)       // -0.5 × 64 - 0.5 × 120
        XCTAssertEqual(halfLeft.rotationY, 30, accuracy: 0.001)
        XCTAssertEqual(halfLeft.scale, 0.95, accuracy: 0.001)

        let far = CrateLayout.transform(index: 0, position: 3, mode: .sideToSide)
        XCTAssertEqual(far.scale, 0.86, accuracy: 0.001)       // 0.9 - 2 × 0.02
        XCTAssertEqual(far.brightness, 0.82, accuracy: 0.001)
        XCTAssertEqual(far.opacity, 1)
        XCTAssertEqual(CrateLayout.transform(index: 9, position: 3, mode: .sideToSide).opacity, 0)
        XCTAssertEqual(CrateLayout.transform(index: 9, position: 3, mode: .sideToSide).brightness, 0.76, accuracy: 0.001)
    }

    func testFrontToBackMatchesThePrototypeBin() {
        let front = CrateLayout.transform(index: 2, position: 2, mode: .frontToBack)
        XCTAssertEqual(front.y, 0)
        XCTAssertEqual(front.scale, 1)
        XCTAssertEqual(front.zIndex, 100)

        let flipped = CrateLayout.transform(index: 1, position: 2, mode: .frontToBack)
        XCTAssertEqual(flipped.y, 150, accuracy: 0.001)
        XCTAssertEqual(flipped.rotationX, -82, accuracy: 0.001)
        XCTAssertEqual(flipped.opacity, 0)
        XCTAssertEqual(flipped.zIndex, 200)

        let tipping = CrateLayout.transform(index: 2, position: 2.5, mode: .frontToBack)
        XCTAssertEqual(tipping.y, 75, accuracy: 0.001)
        XCTAssertEqual(tipping.rotationX, -41, accuracy: 0.001)
        XCTAssertEqual(tipping.opacity, 0.4, accuracy: 0.001)

        let behind = CrateLayout.transform(index: 4, position: 2, mode: .frontToBack)
        XCTAssertEqual(behind.y, -40, accuracy: 0.001)
        XCTAssertEqual(behind.scale, 0.91, accuracy: 0.001)
        XCTAssertEqual(behind.brightness, 0.86, accuracy: 0.001)
        XCTAssertEqual(behind.zIndex, 80)
        XCTAssertEqual(CrateLayout.transform(index: 9, position: 2, mode: .frontToBack).opacity, 0)
    }

    func testModeMetricsIncludingTheNarrowerBinCard() {
        XCTAssertEqual(CrateMode(.sideToSide), .sideToSide)
        XCTAssertEqual(CrateMode(.frontToBack), .frontToBack)
        XCTAssertEqual(CrateMode.sideToSide.cardWidth, 920)
        XCTAssertEqual(CrateMode.frontToBack.cardWidth, 680)
        XCTAssertEqual(CrateMode.sideToSide.dragUnit, 120)
        XCTAssertEqual(CrateMode.frontToBack.dragUnit, 70)
        XCTAssertEqual(CrateLayout.position(focus: 3, dragDelta: -60, mode: .sideToSide), 3.5, accuracy: 0.001)
        XCTAssertEqual(CrateLayout.position(focus: 3, dragDelta: 35, mode: .frontToBack), 2.5, accuracy: 0.001)
    }

    func testDragReleaseStepsWithMomentumAndClamps() {
        XCTAssertEqual(CrateLayout.releasedFocus(focus: 3, count: 10, dragDelta: -130, velocity: 0, mode: .sideToSide), 4)
        XCTAssertEqual(CrateLayout.releasedFocus(focus: 3, count: 10, dragDelta: -50, velocity: 0, mode: .sideToSide), 3)
        // -50 - 0.5 × 320 = -210 → 1.75 → 2 records further.
        XCTAssertEqual(CrateLayout.releasedFocus(focus: 3, count: 10, dragDelta: -50, velocity: -0.5, mode: .sideToSide), 5)
        XCTAssertEqual(CrateLayout.releasedFocus(focus: 3, count: 10, dragDelta: 150, velocity: 0, mode: .frontToBack), 1)
        XCTAssertEqual(CrateLayout.releasedFocus(focus: 1, count: 10, dragDelta: 2_000, velocity: 3, mode: .sideToSide), 0)
        XCTAssertEqual(CrateLayout.releasedFocus(focus: 8, count: 10, dragDelta: -2_000, velocity: -3, mode: .frontToBack), 9)
        XCTAssertEqual(CrateLayout.releasedFocus(focus: 0, count: 0, dragDelta: -500, velocity: 0, mode: .sideToSide), 0)
    }

    func testVisibleWindowAroundFocus() {
        XCTAssertEqual(CrateLayout.visibleIndices(focus: 0, count: 3), 0..<3)
        XCTAssertEqual(CrateLayout.visibleIndices(focus: 10, count: 30), 3..<18)
        XCTAssertEqual(CrateLayout.visibleIndices(focus: 0, count: 0), 0..<0)
    }

    func testWheelStepsOnceThresholdIsCrossed() {
        var wheel = CrateWheelAccumulator()
        XCTAssertEqual(wheel.add(30), 0)
        XCTAssertEqual(wheel.add(30), 1)
        XCTAssertEqual(wheel.total, 0)
        XCTAssertEqual(wheel.add(-20), 0)
        XCTAssertEqual(wheel.add(-40), -1)
        XCTAssertEqual(wheel.add(40), 0)
        XCTAssertEqual(wheel.add(-10), 0, "Changing direction starts over")
        XCTAssertEqual(wheel.total, -10)
        XCTAssertEqual(wheel.add(0.5, precise: false), 1, "A mouse-wheel notch is one record")
        XCTAssertEqual(wheel.add(-3, precise: false), -1)
    }

    func testWheelAxisFollowsTheMode() {
        XCTAssertEqual(CrateWheelAccumulator.axisDelta(deltaX: -10, deltaY: 2, mode: .sideToSide), 10)
        XCTAssertEqual(CrateWheelAccumulator.axisDelta(deltaX: 1, deltaY: -8, mode: .sideToSide), 8)
        XCTAssertEqual(CrateWheelAccumulator.axisDelta(deltaX: -30, deltaY: 4, mode: .frontToBack), -4)
    }

    func testPlaceholderColoursAreStable() {
        XCTAssertEqual(RecordArtwork.placeholderColors(for: "abc").0, RecordArtwork.placeholderColors(for: "abc").0)
    }
}

// MARK: - Crate browser

@MainActor
final class CrateBrowserTests: XCTestCase {
    func testLoadsThePersonalCrateOnceAndStartsNearTheMiddle() async {
        let source = FakeCrateSource()
        let browser = CrateBrowser(source: source, debounce: .zero)
        await browser.loadIfNeeded()
        await browser.loadIfNeeded()
        XCTAssertEqual(source.calls, [.init(kind: .track, query: nil)])
        XCTAssertEqual(browser.phase, .loaded)
        XCTAssertEqual(browser.focus, 2)
        XCTAssertEqual(browser.focusedItem?.title, "Track 2")
        browser.step(10)
        XCTAssertEqual(browser.focus, 4)
        browser.focus = -3
        XCTAssertEqual(browser.focus, 0)
    }

    func testSearchIsDebouncedAndOnlyTheLastQueryIsSent() async {
        let source = FakeCrateSource()
        let browser = CrateBrowser(source: source, debounce: .milliseconds(80))
        browser.setQuery("M")
        browser.setQuery("Mi")
        browser.setQuery("Mil ")
        await browser.settle()
        XCTAssertEqual(source.calls, [.init(kind: .track, query: "Mil")])
        XCTAssertEqual(browser.focus, 0, "Search results start at the best match")
    }

    func testKindSwitchClearsTheSearch() async {
        let source = FakeCrateSource()
        let browser = CrateBrowser(source: source, debounce: .zero)
        browser.setQuery("blue")
        await browser.settle()
        await browser.select(kind: .album)
        XCTAssertEqual(browser.query, "")
        XCTAssertEqual(source.calls.last, .init(kind: .album, query: nil))
        XCTAssertEqual(browser.items.first?.kind, .album)
    }

    func testErrorsAndEmptyResults() async {
        let source = FakeCrateSource()
        source.failure = JukeAPIError.server(status: 503, code: nil, detail: nil)
        let browser = CrateBrowser(source: source, debounce: .zero)
        await browser.reload()
        guard case .failed(let message) = browser.phase else { return XCTFail("Expected failure") }
        XCTAssertFalse(message.isEmpty)
        XCTAssertNil(browser.focusedItem)

        source.failure = nil
        source.count = 0
        await browser.reload()
        XCTAssertEqual(browser.phase, .loaded)
        XCTAssertTrue(browser.items.isEmpty)
        XCTAssertEqual(browser.focus, 0)
    }

    func testRevealFindsARecordInThePersonalCrateWithoutSearching() async {
        let source = FakeCrateSource()
        let browser = CrateBrowser(source: source, debounce: .zero)
        await browser.reveal(kind: .album, spotifyId: "album-4", title: "Album 4")
        XCTAssertEqual(source.calls, [.init(kind: .album, query: nil)])
        XCTAssertEqual(browser.kind, .album)
        XCTAssertEqual(browser.focusedItem?.spotifyId, "album-4")
    }

    func testRevealSearchesByTitleWhenNotInTheCrate() async {
        let source = FakeCrateSource()
        source.searchExtra = Radio.CrateItem(id: "x", kind: .artist, spotifyId: "far-away", title: "Far Away", subtitle: "Artist", artworkUrl: nil, track: nil)
        let browser = CrateBrowser(source: source, debounce: .zero)
        await browser.reveal(kind: .artist, spotifyId: "far-away", title: "Far Away")
        XCTAssertEqual(source.calls, [.init(kind: .artist, query: nil), .init(kind: .artist, query: "Far Away")])
        XCTAssertEqual(browser.query, "Far Away")
        XCTAssertEqual(browser.focusedItem?.spotifyId, "far-away")
    }

    func testRevealWithoutASpotifyIdSearchesByTitle() async {
        let source = FakeCrateSource()
        source.searchExtra = Radio.CrateItem(id: "y", kind: .track, spotifyId: "found", title: "Blue in Green", subtitle: "Miles Davis", artworkUrl: nil, track: nil)
        let browser = CrateBrowser(source: source, debounce: .zero)
        await browser.reveal(kind: .track, spotifyId: "", title: "Blue in Green")
        XCTAssertEqual(source.calls, [.init(kind: .track, query: "Blue in Green")])
        XCTAssertEqual(browser.focusedItem?.spotifyId, "found")
    }

    func testSwitchingKindCancelsAPendingSearch() async {
        let source = FakeCrateSource()
        let browser = CrateBrowser(source: source, debounce: .milliseconds(80))
        browser.setQuery("miles")
        await browser.select(kind: .album)
        await browser.settle()
        XCTAssertEqual(source.calls, [.init(kind: .album, query: nil)])
        XCTAssertEqual(browser.items.first?.kind, .album)
    }

    /// Drives focus the way `LibraryScreen` does: `.task(id: libraryFocus)`
    /// running `appear(coordinator:)`. The focus must stay set while the
    /// reveal is in flight (clearing it would cancel the task) and be cleared
    /// once the record is in front.
    func testFocusFromTheSleeveSurvivesTheTaskThatHandlesIt() async throws {
        let coordinator = JukeCoordinator()
        let source = FakeCrateSource()
        source.delay = .milliseconds(150)
        let browser = CrateBrowser(source: source, debounce: .zero)
        coordinator.focusInLibrary(.init(kind: .album, spotifyId: "album-3", title: "Album 3"))

        let task = Task { await browser.appear(coordinator: coordinator) }
        try await Task.sleep(for: .milliseconds(40))
        XCTAssertNotNil(coordinator.libraryFocus, "Still pending while the crate loads")
        await task.value

        XCTAssertNil(coordinator.libraryFocus)
        XCTAssertEqual(browser.phase, .loaded)
        XCTAssertEqual(browser.kind, .album)
        XCTAssertEqual(browser.focusedItem?.spotifyId, "album-3")
    }

    func testCancelledRevealKeepsTheRequestAndLoadsAgainNextTime() async throws {
        let coordinator = JukeCoordinator()
        let source = FakeCrateSource()
        source.delay = .milliseconds(300)
        let browser = CrateBrowser(source: source, debounce: .zero)
        coordinator.focusInLibrary(.init(kind: .album, spotifyId: "album-1", title: "Album 1"))

        let first = Task { await browser.appear(coordinator: coordinator) }
        try await Task.sleep(for: .milliseconds(40))
        first.cancel()
        await first.value
        XCTAssertEqual(browser.phase, .idle, "A cancelled load is not left loading")
        XCTAssertNotNil(coordinator.libraryFocus, "The request waits for the next appearance")

        source.delay = nil
        await browser.appear(coordinator: coordinator)
        XCTAssertNil(coordinator.libraryFocus)
        XCTAssertEqual(browser.focusedItem?.spotifyId, "album-1")

        // Plain appearance after a cancelled load reloads instead of spinning forever.
        let other = CrateBrowser(source: FakeCrateSource(), debounce: .zero)
        let slow = FakeCrateSource(); slow.delay = .milliseconds(300)
        let cancelled = CrateBrowser(source: slow, debounce: .zero)
        let load = Task { await cancelled.appear(coordinator: JukeCoordinator()) }
        try await Task.sleep(for: .milliseconds(40))
        load.cancel()
        await load.value
        XCTAssertEqual(cancelled.phase, .idle)
        slow.delay = nil
        await cancelled.appear(coordinator: JukeCoordinator())
        XCTAssertEqual(cancelled.phase, .loaded)
        await other.appear(coordinator: JukeCoordinator())
        XCTAssertEqual(other.phase, .loaded)
    }

    func testCoordinatorFocusIsConsumedOnce() async {
        let coordinator = JukeCoordinator()
        let source = FakeCrateSource()
        let browser = CrateBrowser(source: source, debounce: .zero)
        let nothing = await browser.consumeFocus(from: coordinator)
        XCTAssertFalse(nothing)
        XCTAssertTrue(source.calls.isEmpty)

        coordinator.focusInLibrary(.init(kind: .track, spotifyId: "track-3", title: "Track 3"))
        let consumed = await browser.consumeFocus(from: coordinator)
        XCTAssertTrue(consumed)
        XCTAssertNil(coordinator.libraryFocus)
        XCTAssertEqual(browser.focusedItem?.spotifyId, "track-3")
    }
}

// MARK: - New Station rules

@MainActor
final class NewStationFlowTests: XCTestCase {
    private func seed(_ n: Int, kind: Radio.SeedKind = .track) -> Radio.Seed {
        Radio.Seed(kind: kind, spotifyId: "s\(n)", title: "Record \(n)", subtitle: nil, artworkUrl: nil)
    }

    func testPullsUpToThreeAndSwapsOutTheOldest() {
        let flow = NewStationFlow()
        XCTAssertEqual(flow.pullLabel(for: seed(1)), "Pull this record")
        flow.togglePull(seed(1)); flow.togglePull(seed(2)); flow.togglePull(seed(3))
        XCTAssertEqual(flow.pullLabel(for: seed(2)), "Pulled ✓")
        XCTAssertEqual(flow.pullLabel(for: seed(4)), "Swap in this record")
        flow.togglePull(seed(4))
        XCTAssertEqual(flow.seeds.map(\.spotifyId), ["s2", "s3", "s4"])
        flow.togglePull(seed(3))
        XCTAssertEqual(flow.seeds.map(\.spotifyId), ["s2", "s4"])
        XCTAssertFalse(flow.isPulled(seed(3)))
        XCTAssertEqual(flow.pullLabel(for: nil), "Pull this record")
        XCTAssertEqual(flow.pullAccessibilityLabel(for: seed(2)), "Pulled")
        XCTAssertEqual(flow.pullActionName(for: seed(2)), "Put back this record")
        XCTAssertEqual(flow.pullActionName(for: seed(9)), "Pull this record")
    }

    func testFeelingsStopAtTheServerLimit() {
        let flow = NewStationFlow(draft: .init(feelings: (1...15).map { "word \($0)" }))
        XCTAssertEqual(flow.feelings.count, NewStationFlow.maxFeelings)
        XCTAssertTrue(flow.feelingsFull)
        flow.toggleFeeling("🌙")
        XCTAssertFalse(flow.isChosen("🌙"))
        flow.wordsDraft = "one more"
        XCTAssertNil(flow.addWords())
        flow.toggleFeeling("word 1")
        XCTAssertFalse(flow.feelingsFull)
        flow.toggleFeeling("🌙")
        XCTAssertTrue(flow.isChosen("🌙"))
        XCTAssertEqual(flow.createRequest.feelings.count, 12)
    }

    func testPhrasesAreLimitedByCodePointsWithoutSplittingCharacters() {
        let base = String(repeating: "a", count: 39)
        XCTAssertEqual(NewStationFlow.normalizedFeeling(base + "☀️"), base, "☀️ is two code points; it does not fit")
        XCTAssertEqual(NewStationFlow.normalizedFeeling(base + "b"), base + "b")
        let family = "👨‍👩‍👧"   // five code points, one character
        let limited = NewStationFlow.limitedPhrase(String(repeating: family, count: 9))
        XCTAssertEqual(limited, String(repeating: family, count: 8))
        XCTAssertLessThanOrEqual(limited.unicodeScalars.count, 40)
        XCTAssertEqual(NewStationFlow.normalizedFeeling("🔥🔥"), "🔥🔥", "Repeated emoji are kept")
        XCTAssertEqual(NewStationPick.feeling("🔥🔥").text, "🔥🔥")
        XCTAssertEqual(NewStationPick.feeling("rainy 🌧️").text, "“rainy 🌧️”", "Phrases with emoji keep their quotes")
    }

    func testSameIdDifferentKindAreDifferentRecords() {
        let flow = NewStationFlow()
        flow.togglePull(seed(1, kind: .track))
        flow.togglePull(seed(1, kind: .album))
        XCTAssertEqual(flow.seeds.count, 2)
    }

    func testDraftPrefillsStepRecordsAndFeelings() {
        let draft = JukeCoordinator.NewStationDraft(start: .feelings, seeds: [seed(1), seed(1), seed(2), seed(3), seed(4)], feelings: ["🌙", "  late   drive ", ""])
        let flow = NewStationFlow(draft: draft)
        XCTAssertEqual(flow.step, .feelings)
        XCTAssertEqual(flow.path, .feelings)
        XCTAssertEqual(flow.seeds.map(\.spotifyId), ["s1", "s2", "s3"])
        XCTAssertEqual(flow.feelings, ["🌙", "late drive"])
        XCTAssertTrue(flow.feelingTokens.contains("late drive"))
    }

    func testWordsBecomeFeelings() {
        let flow = NewStationFlow()
        flow.wordsDraft = "   rainy   train ride home "
        XCTAssertEqual(flow.addWords(), "rainy train ride home")
        XCTAssertEqual(flow.wordsDraft, "")
        flow.wordsDraft = "🌧️"
        XCTAssertEqual(flow.addWords(), "🌧️")
        flow.wordsDraft = "   "
        XCTAssertNil(flow.addWords())
        flow.wordsDraft = String(repeating: "a", count: 60)
        XCTAssertEqual(flow.addWords()?.count, 40)
        XCTAssertEqual(flow.feelings.count, 3)
        XCTAssertEqual(flow.customFeelings.count, 2, "Vocabulary emoji are not duplicated as custom tokens")
        XCTAssertTrue(NewStationFlow.isEmoji("☀️"))
        XCTAssertFalse(NewStationFlow.isEmoji("7"))
        XCTAssertFalse(NewStationFlow.isEmoji("nights"))
    }

    func testPickedListShowsRecordsThenFeelingsAndCanBeEdited() {
        let flow = NewStationFlow()
        flow.togglePull(Radio.Seed(kind: .track, spotifyId: "mc", title: "Midnight City", subtitle: "M83", artworkUrl: nil))
        flow.togglePull(Radio.Seed(kind: .album, spotifyId: "n", title: "Nights", subtitle: nil, artworkUrl: nil))
        flow.toggleFeeling("🌙")
        flow.wordsDraft = "rainy train ride home"
        flow.addWords()
        XCTAssertEqual(flow.picks.map(\.text), ["Midnight City", "Nights", "🌙", "“rainy train ride home”"])
        flow.remove(flow.picks[1])
        flow.remove(.feeling("🌙"))
        XCTAssertEqual(flow.picks.map(\.text), ["Midnight City", "“rainy train ride home”"])
        flow.toggleFeeling("rainy train ride home")
        XCTAssertEqual(flow.picks.count, 1)
        XCTAssertTrue(flow.feelingTokens.contains("rainy train ride home"), "Your own words stay as a token")
    }

    func testStartNeedsARecordOrAFeelingAndNamesTheStation() {
        let flow = NewStationFlow()
        XCTAssertFalse(flow.canStart)
        XCTAssertEqual(flow.startLabel, "Pick a record or a feeling")
        flow.toggleFeeling("🌙"); flow.toggleFeeling("✨")
        XCTAssertTrue(flow.canStart)
        XCTAssertEqual(flow.startLabel, "Start 🌙 ✨ Radio")
        flow.togglePull(seed(7))
        XCTAssertEqual(flow.stationName, "Record 7 Radio")
        XCTAssertEqual(flow.createRequest, Radio.CreateStationRequest(name: nil, seeds: [seed(7)], feelings: ["🌙", "✨"]))
    }

    func testStepsAndOptionalLinks() {
        let flow = NewStationFlow()
        XCTAssertEqual(flow.otherStepLabel, "Add a feeling (optional)")
        XCTAssertEqual(flow.stepLine, "Pull up to three records. Feelings are optional.")
        flow.select(.feelings)                  // nothing chosen: the tab changes the main step
        XCTAssertEqual(flow.path, .feelings)
        XCTAssertEqual(flow.otherStepLabel, "Add records (optional)")
        flow.toggleFeeling("😌")
        flow.goToOtherStep()
        XCTAssertEqual(flow.step, .records)
        XCTAssertEqual(flow.path, .feelings)
        XCTAssertEqual(flow.otherStepLabel, "Back to feelings")
        XCTAssertEqual(flow.stepLine, "Pull up to three records. Your feelings are saved.")
        flow.select(.feelings)
        XCTAssertEqual(flow.otherStepLabel, "Add records (optional)")
    }

    func testHeadingsAndPreview() {
        let flow = NewStationFlow()
        XCTAssertEqual(flow.feelingsHeading, "What do you want to feel?")
        XCTAssertEqual(flow.previewCaption, "Pick a feeling and the crate fills up")
        let crate = (0..<10).map { Radio.CrateItem(id: Radio.ID(integerLiteral: $0), kind: .track, spotifyId: "s\($0)", title: "Record \($0)", subtitle: nil, artworkUrl: nil, track: nil) }
        flow.togglePull(seed(5)); flow.togglePull(seed(6))
        XCTAssertEqual(flow.feelingsHeading, "How should Record 5 & co. feel?")
        XCTAssertEqual(flow.previewRecords(from: crate).map(\.spotifyId), ["s5", "s6", "s0", "s1", "s2", "s3", "s4"])
    }
}

// MARK: - Starting stations (mock API)

@MainActor
final class StationStarterTests: XCTestCase {
    func testStartingCreatesTheStationAndQueuesItAfterTheCurrentSong() async throws {
        let recorder = LibraryRecordedRequests()
        let api = makeLibraryAPI(recorder: recorder) { _ in (201, Data(stationJSON.utf8)) }
        let coordinator = JukeCoordinator()
        coordinator.openNewStation(.init(start: .feelings))
        let seeds = (1...4).map { Radio.Seed(kind: .track, spotifyId: "s\($0)", title: "T\($0)", subtitle: nil, artworkUrl: nil) }

        let station = try await StationStarter(creator: api, coordinator: coordinator).start(seeds: seeds, feelings: ["🌙"])

        XCTAssertEqual(station.id.rawValue, "8d1b1b4e-1111-4c3e-9a55-7b1d2f3e4a5b")
        XCTAssertEqual(coordinator.stationRequest, .init(stationID: station.id, timing: .afterCurrentSong))
        XCTAssertEqual(coordinator.radioRoute, .nowPlaying)
        let request = try XCTUnwrap(recorder.all.first)
        XCTAssertEqual(request.method, "POST")
        XCTAssertEqual(request.path, "/api/v1/radio/stations/")
        let body = try JSONSerialization.jsonObject(with: Data(try XCTUnwrap(request.body).utf8)) as? [String: Any]
        XCTAssertEqual((body?["seeds"] as? [[String: Any]])?.compactMap { $0["spotifyId"] as? String }, ["s1", "s2", "s3"], "At most three records")
        XCTAssertEqual(body?["feelings"] as? [String], ["🌙"])
        XCTAssertNil(body?["name"], "The server names the station")
    }

    func testFailedCreationLeavesTheRadioAlone() async {
        let api = makeLibraryAPI { _ in (400, Data(#"{"detail":"Pick at least one seed or feeling."}"#.utf8)) }
        let coordinator = JukeCoordinator()
        do {
            try await StationStarter(creator: api, coordinator: coordinator).start(seeds: [], feelings: [])
            XCTFail("Expected a rejection")
        } catch {
            XCTAssertEqual((error as? JukeAPIError)?.detail, "Pick at least one seed or feeling.")
        }
        XCTAssertNil(coordinator.stationRequest)
    }

    func testCrateSearchRequestThroughTheAPI() async throws {
        let recorder = LibraryRecordedRequests()
        let api = makeLibraryAPI(recorder: recorder) { _ in (200, Data(#"{"items":[{"id":"a1","kind":"album","spotifyId":"1weenld61qoidwYuZ1GESA","title":"Kind of Blue","subtitle":"Miles Davis","artworkUrl":null}]}"#.utf8)) }
        let browser = CrateBrowser(source: api, debounce: .zero)
        await browser.select(kind: .album)
        browser.setQuery("kind of blue")
        await browser.settle()
        XCTAssertEqual(recorder.all.map(\.query), ["kind=albums", "kind=albums&q=kind%20of%20blue"])
        XCTAssertEqual(browser.focusedItem?.title, "Kind of Blue")
    }
}

// MARK: - Helpers

private final class FakeCrateSource: CrateSource, @unchecked Sendable {
    struct Call: Equatable { var kind: Radio.SeedKind; var query: String? }
    private let lock = NSLock()
    private var recorded: [Call] = []
    var failure: Error?
    var count = 5
    var searchExtra: Radio.CrateItem?
    /// Simulated latency; honours task cancellation like URLSession does.
    var delay: Duration?

    var calls: [Call] { lock.withLock { recorded } }

    func crate(kind: Radio.SeedKind, query: String?) async throws -> [Radio.CrateItem] {
        let (failure, count, extra) = lock.withLock { () -> (Error?, Int, Radio.CrateItem?) in
            recorded.append(Call(kind: kind, query: query))
            return (self.failure, self.count, self.searchExtra)
        }
        if let failure { throw failure }
        if let delay = lock.withLock({ self.delay }) { try await Task.sleep(for: delay) }
        var items = (0..<count).map { n in
            Radio.CrateItem(id: Radio.ID("\(kind.rawValue)-\(n)"), kind: kind, spotifyId: "\(kind.rawValue)-\(n)", title: "\(kind.rawValue.capitalized) \(n)", subtitle: nil, artworkUrl: nil, track: nil)
        }
        if query != nil, let extra { items.insert(extra, at: 0) }
        return items
    }
}

private let stationJSON = """
{"id":"8d1b1b4e-1111-4c3e-9a55-7b1d2f3e4a5b","name":"T1 Radio","kind":"custom","frequency":107.9,
 "seeds":[{"kind":"track","spotifyId":"s1","title":"T1","subtitle":null,"artworkUrl":null}],
 "thumbnails":[],"feelings":["🌙"],"learning":true,"exclusions":[],"createdAt":"2026-10-01T12:00:00Z"}
"""

private struct LibraryRecordedRequest: Sendable {
    let method: String
    let path: String
    let query: String?
    let body: String?
}

private final class LibraryRecordedRequests: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [LibraryRecordedRequest] = []
    func append(_ value: LibraryRecordedRequest) { lock.withLock { values.append(value) } }
    var all: [LibraryRecordedRequest] { lock.withLock { values } }
}

private func makeLibraryAPI(
    recorder: LibraryRecordedRequests = LibraryRecordedRequests(),
    handler: @escaping @Sendable (URLRequest) throws -> (Int, Data)
) -> JukeAPI {
    let host = "\(UUID().uuidString.lowercased()).library-tests.example"
    LibraryURLProtocol.handlers.set({ request in
        let components = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)
        recorder.append(LibraryRecordedRequest(
            method: request.httpMethod ?? "GET",
            path: request.url!.path(percentEncoded: true),
            query: components?.percentEncodedQuery,
            body: request.libraryBody().map { String(decoding: $0, as: UTF8.self) }
        ))
        return try handler(request)
    }, host: host)
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [LibraryURLProtocol.self]
    return JukeAPI(baseURL: URL(string: "https://\(host)/")!, session: URLSession(configuration: config), token: { "secret-token" })
}

private final class LibraryRequestHandlers: @unchecked Sendable {
    typealias Handler = @Sendable (URLRequest) throws -> (Int, Data)
    private let lock = NSLock()
    private var values: [String: Handler] = [:]
    func set(_ handler: @escaping Handler, host: String) { lock.withLock { values[host] = handler } }
    func get(host: String) -> Handler? { lock.withLock { values[host] } }
}

private final class LibraryURLProtocol: URLProtocol, @unchecked Sendable {
    static let handlers = LibraryRequestHandlers()
    override class func canInit(with request: URLRequest) -> Bool { request.url?.host?.hasSuffix("library-tests.example") == true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let url = request.url, let host = url.host, let handler = Self.handlers.get(host: host) else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }
        do {
            let (status, data) = try handler(request)
            let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}

private extension URLRequest {
    func libraryBody() -> Data? {
        if let httpBody { return httpBody }
        guard let stream = httpBodyStream else { return nil }
        stream.open(); defer { stream.close() }
        var result = Data(); var bytes = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let count = stream.read(&bytes, maxLength: bytes.count)
            if count <= 0 { break }
            result.append(contentsOf: bytes.prefix(count))
        }
        return result
    }
}
