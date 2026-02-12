import Foundation
#if canImport(UIKit)
import UIKit
#endif

/// Provides utilities for handling deep links.
///
/// ## Usage
///
/// ```swift
/// // Handle email verification
/// Task {
///     do {
///         let result = try await JukeDeepLinkHandler.handleVerification(
///             userId: "123",
///             timestamp: "abc",
///             signature: "xyz",
///             authService: authService
///         )
///         if let token = result.token, let username = result.username {
///             session.authenticateWithToken(token, username: username)
///         }
///     } catch {
///         // Show error
///     }
/// }
///
/// // Try to open Juke app for registration
/// if !JukeDeepLinkHandler.openJukeAppForRegistration() {
///     // Fall back to web URL
///     UIApplication.shared.open(webRegistrationURL)
/// }
/// ```
public enum JukeDeepLinkHandler {

    /// Handles email verification by calling the auth service.
    /// - Parameters:
    ///   - userId: The user ID from the verification link.
    ///   - timestamp: The timestamp from the verification link.
    ///   - signature: The signature from the verification link.
    ///   - authService: The auth service to use for verification.
    /// - Returns: The verification response (may include token for auto-login).
    /// - Throws: `JukeAPIError` on failure.
    public static func handleVerification(
        userId: String,
        timestamp: String,
        signature: String,
        authService: JukeAuthService
    ) async throws -> JukeVerifyResponse {
        try await authService.verifyRegistration(
            userId: userId,
            timestamp: timestamp,
            signature: signature
        )
    }

    #if canImport(UIKit)
    /// Attempts to open the Juke app for registration.
    ///
    /// This is used by satellite apps (ShotClock, TuneTrivia) to redirect users
    /// to the main Juke app for registration.
    ///
    /// - Parameter scheme: The URL scheme of the Juke app. Defaults to "juke".
    /// - Returns: `true` if the app was opened, `false` if the app is not installed.
    @MainActor
    public static func openJukeAppForRegistration(scheme: String = "juke") -> Bool {
        guard let url = URL(string: "\(scheme)://register") else {
            return false
        }

        guard UIApplication.shared.canOpenURL(url) else {
            return false
        }

        UIApplication.shared.open(url)
        return true
    }

    /// Opens a URL in the default browser or app.
    /// - Parameter url: The URL to open.
    @MainActor
    public static func openURL(_ url: URL) {
        UIApplication.shared.open(url)
    }
    #endif

    /// Creates a registration fallback URL for web registration.
    ///
    /// Used when the Juke app is not installed and registration needs to
    /// fall back to a web-based flow.
    ///
    /// - Parameter configuration: The API configuration containing the frontend URL.
    /// - Returns: The web registration URL, or `nil` if not configured.
    public static func webRegistrationURL(configuration: JukeAPIConfiguration) -> URL? {
        guard let frontendURL = configuration.frontendURL else {
            return nil
        }
        return frontendURL.appendingPathComponent("register")
    }
}
