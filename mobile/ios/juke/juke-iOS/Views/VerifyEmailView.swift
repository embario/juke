import SwiftUI

enum VerificationState {
    case loading
    case success
    case error(String)
}

struct VerifyEmailView: View {
    @EnvironmentObject private var session: SessionStore
    @State private var state: VerificationState = .loading

    private let userId: String
    private let timestamp: String
    private let signature: String

    private let authService = AuthService()

    init(userId: String, timestamp: String, signature: String) {
        self.userId = userId
        self.timestamp = timestamp
        self.signature = signature
    }

    var body: some View {
        NavigationStack {
            ZStack {
                JukeBackground()
                ScrollView(showsIndicators: false) {
                    VStack(spacing: 32) {
                        Spacer(minLength: 60)
                        JukeCard {
                            VStack(alignment: .center, spacing: 24) {
                                switch state {
                                case .loading:
                                    JukeSpinner()
                                    Text("Verifying your account…")
                                        .font(.headline)
                                        .foregroundColor(JukePalette.text)
                                    Text("Please wait while we confirm your email.")
                                        .font(.subheadline)
                                        .foregroundColor(JukePalette.muted)

                                case .success:
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.system(size: 64))
                                        .foregroundColor(JukePalette.success)
                                    Text("Account Verified!")
                                        .font(.title.bold())
                                        .foregroundColor(JukePalette.text)
                                    Text("Your account has been verified. Redirecting you to onboarding…")
                                        .font(.subheadline)
                                        .foregroundColor(JukePalette.muted)
                                        .multilineTextAlignment(.center)

                                case .error(let message):
                                    Image(systemName: "xmark.circle.fill")
                                        .font(.system(size: 64))
                                        .foregroundColor(JukePalette.error)
                                    Text("Verification Failed")
                                        .font(.title.bold())
                                        .foregroundColor(JukePalette.text)
                                    Text(message)
                                        .font(.subheadline)
                                        .foregroundColor(JukePalette.muted)
                                        .multilineTextAlignment(.center)
                                }
                            }
                            .padding(.vertical, 16)
                        }
                        Spacer()
                    }
                    .padding(.horizontal, 24)
                }
            }
            .toolbar(.hidden, for: .navigationBar)
        }
        .task {
            await performVerification()
        }
    }

    private func performVerification() async {
        do {
            let response = try await authService.verifyRegistration(
                userId: userId,
                timestamp: timestamp,
                signature: signature
            )
            if let token = response.token, let username = response.username {
                session.authenticateWithToken(token, username: username)
            }
            state = .success
            // Auto-navigate to onboarding after a brief pause
            // ContentView will switch to authenticated state which shows SearchDashboardView;
            // the onboarding flow is handled via the navigation stack in the authenticated view.
        } catch {
            let message: String
            if let apiError = error as? APIError {
                switch apiError {
                case .server(_, let msg):
                    message = msg
                default:
                    message = "Verification failed. The link may have expired."
                }
            } else {
                message = error.localizedDescription
            }
            state = .error(message)
        }
    }
}

#Preview {
    VerifyEmailView(userId: "1", timestamp: "abc", signature: "xyz")
        .environmentObject(SessionStore())
}
