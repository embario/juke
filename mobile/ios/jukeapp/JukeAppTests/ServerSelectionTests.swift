import Foundation
import Testing
@testable import JukeApp

@Suite(.serialized) struct ServerSelectionTests {
    private func reset() {
        UserDefaults.standard.removeObject(forKey: JukeServer.backendURLKey)
        JukeServer.fallbackBaseURL = nil
    }

    @Test func settingsValueBeatsLaunchFallback() {
        reset(); defer { reset() }
        JukeServer.fallbackBaseURL = URL(string: "http://127.0.0.1:8000/")
        #expect(AppConfiguration.currentBackendURL.absoluteString == "http://127.0.0.1:8000/")
        UserDefaults.standard.set("https://juke.example.com/", forKey: JukeServer.backendURLKey)
        #expect(AppConfiguration.currentBackendURL.absoluteString == "https://juke.example.com/")
        #expect(AppConfiguration.currentFrontendURL.absoluteString == "https://juke.example.com/")
        #expect(AppConfiguration.currentAPIBaseURL.absoluteString == "https://juke.example.com/api/v1/")
    }

    @Test func fallsBackToNeptuneWhenNothingIsSet() {
        reset(); defer { reset() }
        #expect(AppConfiguration.currentBackendURL == JukeServer.defaultBaseURL)
    }

    @Test func plainHTTPIsOnlyAcceptedForLoopback() {
        #expect(JukeServer.normalizedBaseURL("http://example.com") == nil)
        #expect(JukeServer.normalizedBaseURL("http://localhost:8000/api/v1")?.absoluteString == "http://localhost:8000/")
    }

    @Test func tabsCoverTheFiveSections() {
        #expect(JukeTab.allCases.map(\.title) == ["Radio", "Library", "Memories", "Chat", "Settings"])
    }
}
