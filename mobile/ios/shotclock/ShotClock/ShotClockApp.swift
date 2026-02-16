import SwiftUI
import JukeKit

@main
struct ShotClockApp: App {
    @StateObject private var session = JukeSessionStore(keyPrefix: "shotclock")

    private let deepLinkParser = JukeDeepLinkParser(
        schemes: ["shotclock"],
        universalLinkHosts: []
    )

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(session)
                .onOpenURL { url in
                    Task {
                        await handleDeepLink(url)
                    }
                }
        }
    }

    @MainActor
    private func handleDeepLink(_ url: URL) async {
        guard let deepLink = deepLinkParser.parse(url) else { return }

        switch deepLink {
        case .verifyUser(let userId, let timestamp, let signature):
            await handleVerification(userId: userId, timestamp: timestamp, signature: signature)
        case .register, .custom:
            break
        }
    }

    @MainActor
    private func handleVerification(userId: String, timestamp: String, signature: String) async {
        do {
            let authService = JukeAuthService()
            _ = try await JukeDeepLinkHandler.handleVerification(
                userId: userId,
                timestamp: timestamp,
                signature: signature,
                authService: authService
            )
            session.verificationMessage = "Email verified! You can now log in."
        } catch let error as JukeAPIError {
            switch error {
            case .server(_, let msg):
                session.verificationMessage = msg
            default:
                session.verificationMessage = "Verification failed."
            }
        } catch {
            session.verificationMessage = "Verification failed: \(error.localizedDescription)"
        }
    }
}
