import SwiftUI

@MainActor
final class SessionLobbyViewModel: ObservableObject {
    @Published var session: PowerHourSession
    @Published var players: [SessionPlayer] = []
    @Published var tracks: [SessionTrackItem] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let sessionService: SessionService

    init(session: PowerHourSession, sessionService: SessionService = SessionService()) {
        self.session = session
        self.sessionService = sessionService
    }

    func loadDetails(token: String?) async {
        guard let token else { return }
        isLoading = true
        defer { isLoading = false }

        async let fetchedPlayers = sessionService.getPlayers(sessionId: session.id, token: token)
        async let fetchedTracks = sessionService.getTracks(sessionId: session.id, token: token)
        async let fetchedSession = sessionService.getSession(id: session.id, token: token)

        do {
            let (p, t, s) = try await (fetchedPlayers, fetchedTracks, fetchedSession)
            players = p
            tracks = t
            session = s

            // Auto-navigate to playback if session is already active or paused
            if s.status == .active || s.status == .paused {
                didStartSession = true
            }
        } catch {
            // Partial load is OK, don't show error on initial load
        }
    }

    func refresh(token: String?) async {
        guard let token else { return }
        do {
            async let fetchedPlayers = sessionService.getPlayers(sessionId: session.id, token: token)
            async let fetchedTracks = sessionService.getTracks(sessionId: session.id, token: token)
            async let fetchedSession = sessionService.getSession(id: session.id, token: token)

            let (p, t, s) = try await (fetchedPlayers, fetchedTracks, fetchedSession)
            players = p
            tracks = t
            session = s
        } catch {
            // Silent refresh failure
        }
    }

    @Published var didStartSession = false

    func startSession(token: String?) async {
        guard let token else { return }
        errorMessage = nil
        do {
            let state = try await sessionService.startSession(id: session.id, token: token)
            session = try await sessionService.getSession(id: session.id, token: token)
            didStartSession = true
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    var isAdmin: Bool {
        // Check if current user is the admin based on the admin field
        // We compare with the players list to find admin
        players.first(where: { $0.isAdmin })?.user.id == session.admin
    }
}
