import Foundation
import Testing
@testable import JukeApp

struct AppConfigurationTests {
    @Test func defaultsToNeptuneWhenUnset() {
        let config = AppConfiguration(environment: ["BACKEND_URL": "", "FRONTEND_URL": "  "], bundle: Bundle(for: BundleToken.self))
        #expect(config.backendURL == AppConfiguration.defaultBackendURL)
        #expect(config.frontendURL == AppConfiguration.defaultBackendURL)
        #expect(config.apiBaseURL.absoluteString == "https://neptune.tail647b75.ts.net/api/v1/")
    }

    @Test func environmentOverridesAndNormalizes() {
        let config = AppConfiguration(environment: ["BACKEND_URL": "http://127.0.0.1:8000/api/v1/", "FRONTEND_URL": "http://127.0.0.1:5173"], bundle: Bundle(for: BundleToken.self))
        #expect(config.backendURL.absoluteString == "http://127.0.0.1:8000/")
        #expect(config.apiBaseURL.absoluteString == "http://127.0.0.1:8000/api/v1/")
        #expect(config.frontendURL.absoluteString == "http://127.0.0.1:5173/")
    }

    @Test func frontendFallsBackToBackend() {
        let config = AppConfiguration(environment: ["BACKEND_URL": "https://juke.example.com"], bundle: Bundle(for: BundleToken.self))
        #expect(config.frontendURL.absoluteString == "https://juke.example.com/")
    }

    @Test func rejectsUnexpandedAndNonHTTPValues() {
        #expect(AppConfiguration.normalized("$(BACKEND_URL)") == nil)
        #expect(AppConfiguration.normalized("ftp://example.com") == nil)
        #expect(AppConfiguration.normalized("not a url") == nil)
    }

    @Test func signInUsesJukeAppCallback() {
        #expect(JukeAuthService.clientID == "juke-app-ios")
        #expect(JukeAuthService.redirectURI == "juke-app://auth/callback")
        #expect(JukeAuthService.redirectURI.hasPrefix(JukeAuthService.callbackScheme + "://"))
    }
}

private final class BundleToken {}
