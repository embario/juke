import SwiftUI

@main
struct ShotClockApp: App {
    @StateObject private var session = SessionStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(session)
                .environmentObject(SpotifyManager.shared)
                .onOpenURL { url in
                    Task {
                        await handleDeepLink(url)
                    }
                }
                .onReceive(NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)) { _ in
                    SpotifyManager.shared.connect()
                }
        }
    }

    @MainActor
    private func handleDeepLink(_ url: URL) async {
        guard url.scheme == "shotclock" else { return }

        switch url.host {
        case "verify-user":
            await handleVerification(url: url)
        case "spotify-callback":
            SpotifyManager.shared.handleRedirectURL(url)
        default:
            break
        }
    }

    @MainActor
    private func handleVerification(url: URL) async {
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let queryItems = components.queryItems else {
            session.verificationMessage = "Invalid verification link."
            return
        }

        let userId = queryItems.first(where: { $0.name == "user_id" })?.value
        let timestamp = queryItems.first(where: { $0.name == "timestamp" })?.value
        let signature = queryItems.first(where: { $0.name == "signature" })?.value

        guard let userId, let timestamp, let signature else {
            session.verificationMessage = "Verification link is missing required parameters."
            return
        }

        do {
            try await AuthService().verifyRegistration(
                userId: userId,
                timestamp: timestamp,
                signature: signature
            )
            session.verificationMessage = "Email verified! You can now log in."
        } catch let error as APIError {
            session.verificationMessage = error.errorDescription ?? "Verification failed."
        } catch {
            session.verificationMessage = "Verification failed: \(error.localizedDescription)"
        }
    }
}
