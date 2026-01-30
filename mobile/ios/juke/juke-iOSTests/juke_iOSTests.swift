//
//  juke_iOSTests.swift
//  juke-iOSTests
//
//  Created by Mario Barrenechea on 3/28/22.
//

import XCTest
@testable import juke_iOS

class juke_iOSTests: XCTestCase {

    override func setUpWithError() throws {
        // Put setup code here. This method is called before the invocation of each test method in the class.
    }

    override func tearDownWithError() throws {
        // Put teardown code here. This method is called after the invocation of each test method in the class.
    }

    func testExample() throws {
        // This is an example of a functional test case.
        // Use XCTAssert and related functions to verify your tests produce the correct results.
        // Any test you write for XCTest can be annotated as throws and async.
        // Mark your test throws to produce an unexpected failure when your test encounters an uncaught error.
        // Mark your test async to allow awaiting for asynchronous code to complete. Check the results with assertions afterwards.
    }

    func testPerformanceExample() throws {
        // This is an example of a performance test case.
        self.measure {
            // Put the code you want to measure the time of here.
        }
    }

    func testAppConfigurationEnvOverridesPlist() {
        let config = AppConfiguration(
            env: ["DISABLE_REGISTRATION": "true"],
            plistValue: "false"
        )

        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testAppConfigurationPlistBooleanFallback() {
        let config = AppConfiguration(
            env: [:],
            plistValue: true
        )

        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testAPIConfigurationEnvOverridesPlist() {
        let config = APIConfiguration(
            environment: ["BACKEND_URL": "http://env.example.com"],
            backendPlist: "http://plist.example.com",
            frontendPlist: nil
        )

        XCTAssertEqual(config.baseURL.absoluteString, "http://env.example.com")
    }

    func testAPIConfigurationPlistFallback() {
        let config = APIConfiguration(
            environment: [:],
            backendPlist: "http://plist.example.com",
            frontendPlist: nil
        )

        XCTAssertEqual(config.baseURL.absoluteString, "http://plist.example.com")
    }

}

@MainActor
final class OnboardingStoreTests: XCTestCase {
    private func makeDefaults() -> UserDefaults {
        let suiteName = "juke-iOS.tests.onboarding.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)
        return defaults
    }

    func testDraftPersistsPerUserKey() {
        let defaults = makeDefaults()
        let storeA = OnboardingStore(userKey: "user-a", defaults: defaults)
        storeA.toggleFavoriteGenre("rock")

        let storeA2 = OnboardingStore(userKey: "user-a", defaults: defaults)
        XCTAssertEqual(storeA2.data.favoriteGenres, ["rock"])

        let storeB = OnboardingStore(userKey: "user-b", defaults: defaults)
        XCTAssertTrue(storeB.data.favoriteGenres.isEmpty)
    }

    func testMarkCompletedClearsDraft() {
        let defaults = makeDefaults()
        let store = OnboardingStore(userKey: "user-a", defaults: defaults)
        store.toggleFavoriteGenre("pop")
        store.markCompleted()

        XCTAssertTrue(OnboardingStore.isCompleted(for: "user-a", defaults: defaults))
        let refreshed = OnboardingStore(userKey: "user-a", defaults: defaults)
        XCTAssertTrue(refreshed.data.favoriteGenres.isEmpty)
    }

    func testFavoriteGenreToggleRespectsLimit() {
        let defaults = makeDefaults()
        let store = OnboardingStore(userKey: "user-a", defaults: defaults)
        store.toggleFavoriteGenre("rock")
        store.toggleFavoriteGenre("pop")
        store.toggleFavoriteGenre("jazz")
        store.toggleFavoriteGenre("hiphop")

        XCTAssertEqual(store.data.favoriteGenres.count, 3)
        XCTAssertFalse(store.data.favoriteGenres.contains("hiphop"))
    }

    func testSearchCitiesIsCaseInsensitiveAndLimited() {
        let results = searchCities("an")
        XCTAssertTrue(results.contains(where: { $0.name == "San Francisco" }))
        XCTAssertLessThanOrEqual(results.count, 10)
    }
}
