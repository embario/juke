import SwiftUI

@MainActor
final class HomeViewModel: ObservableObject {
    @Published var sessions: [PowerHourSession] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var joinCode = ""
    @Published var isShowingJoinSheet = false
    @Published var joinError: String?
    @Published var isJoining = false

    private let sessionService: SessionService

    init(sessionService: SessionService = SessionService()) {
        self.sessionService = sessionService
    }

    func loadSessions(token: String?) async {
        guard let token else { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            sessions = try await sessionService.listSessions(token: token)
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func joinSession(token: String?) async -> PowerHourSession? {
        guard let token else { return nil }
        let code = joinCode.trimmingCharacters(in: .whitespaces)
        guard !code.isEmpty else {
            joinError = "Enter an invite code."
            return nil
        }

        isJoining = true
        joinError = nil
        defer { isJoining = false }

        do {
            let session = try await sessionService.joinSession(inviteCode: code, token: token)
            joinCode = ""
            isShowingJoinSheet = false
            // Add to local list
            if !sessions.contains(where: { $0.id == session.id }) {
                sessions.insert(session, at: 0)
            }
            return session
        } catch let error as APIError {
            joinError = error.errorDescription
            return nil
        } catch {
            joinError = error.localizedDescription
            return nil
        }
    }

    func deleteSession(id: String, token: String?) async {
        guard let token else { return }
        do {
            try await sessionService.deleteSession(id: id, token: token)
            sessions.removeAll { $0.id == id }
        } catch {
            errorMessage = "Failed to delete session."
        }
    }
}
