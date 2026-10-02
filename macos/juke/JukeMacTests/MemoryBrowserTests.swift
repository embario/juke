import XCTest
@testable import Juke

final class MemoryBrowserTests: XCTestCase {
    private let ids = (0..<3).map { _ in UUID() }

    func testStartsOnTheFirstMemoryAndShowsPosition() {
        var browser = MemoryBrowser()
        XCTAssertEqual(browser.positionLabel, "")
        XCTAssertFalse(browser.canFlip)
        browser.update(ids: ids)
        XCTAssertEqual(browser.currentID, ids[0])
        XCTAssertEqual(browser.positionLabel, "1 of 3")
        XCTAssertTrue(browser.canFlip)
    }

    func testFlippingWrapsAtBothEndsAndRemembersDirection() {
        var browser = MemoryBrowser()
        browser.update(ids: ids)
        browser.previous()
        XCTAssertEqual(browser.currentID, ids[2])
        XCTAssertEqual(browser.direction, .backward)
        browser.next()
        XCTAssertEqual(browser.currentID, ids[0])
        XCTAssertEqual(browser.direction, .forward)
        browser.next(); browser.next()
        XCTAssertEqual(browser.positionLabel, "3 of 3")
    }

    func testSingleMemoryDoesNotFlipAway() {
        var browser = MemoryBrowser()
        browser.update(ids: [ids[0]])
        browser.next()
        XCTAssertEqual(browser.currentID, ids[0])
        XCTAssertFalse(browser.canFlip)
    }

    func testRefreshKeepsTheCurrentMemoryEvenWhenItMoves() {
        var browser = MemoryBrowser()
        browser.update(ids: ids)
        browser.next()
        let newer = UUID()
        browser.update(ids: [newer] + ids)
        XCTAssertEqual(browser.currentID, ids[1])
        XCTAssertEqual(browser.positionLabel, "3 of 4")
    }

    func testRemovedMemoryFallsBackToTheSamePosition() {
        var browser = MemoryBrowser()
        browser.update(ids: ids)
        browser.next(); browser.next()
        browser.update(ids: [ids[0], ids[1]])
        XCTAssertEqual(browser.currentID, ids[1])
        browser.update(ids: [])
        XCTAssertNil(browser.currentID)
        XCTAssertEqual(browser.positionLabel, "")
    }

    func testSelectingSetsDirectionAndPendingSelectionAppliesWhenListed() {
        var browser = MemoryBrowser()
        browser.update(ids: ids)
        browser.select(ids[2])
        XCTAssertEqual(browser.direction, .forward)
        browser.select(ids[0])
        XCTAssertEqual(browser.direction, .backward)

        let saved = UUID()
        browser.select(saved)
        XCTAssertEqual(browser.pendingID, saved)
        browser.update(ids: ids)          // search still hides it
        XCTAssertNotNil(browser.currentID)
        browser.update(ids: [saved] + ids) // search cleared
        XCTAssertEqual(browser.currentID, saved)
        XCTAssertNil(browser.pendingID)
        XCTAssertEqual(browser.positionLabel, "1 of 4")
    }
}
