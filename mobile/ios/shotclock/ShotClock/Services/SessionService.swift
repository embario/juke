import Foundation

struct SessionService {
    private let api: APIClient

    init(api: APIClient = .shared) {
        self.api = api
    }

    func listSessions(token: String) async throws -> [PowerHourSession] {
        try await api.get("/powerhour/sessions/", token: token)
    }

    func createSession(request: CreateSessionRequest, token: String) async throws -> PowerHourSession {
        try await api.post("/powerhour/sessions/", body: request, token: token)
    }

    func joinSession(inviteCode: String, token: String) async throws -> PowerHourSession {
        let body = JoinSessionRequest(inviteCode: inviteCode)
        return try await api.post("/powerhour/sessions/join/", body: body, token: token)
    }

    func getSession(id: String, token: String) async throws -> PowerHourSession {
        try await api.get("/powerhour/sessions/\(id)/", token: token)
    }

    func deleteSession(id: String, token: String) async throws {
        try await api.delete("/powerhour/sessions/\(id)/", token: token)
    }

    func getPlayers(sessionId: String, token: String) async throws -> [SessionPlayer] {
        try await api.get("/powerhour/sessions/\(sessionId)/players/", token: token)
    }

    func getTracks(sessionId: String, token: String) async throws -> [SessionTrackItem] {
        try await api.get("/powerhour/sessions/\(sessionId)/tracks/", token: token)
    }

    func startSession(id: String, token: String) async throws -> SessionState {
        try await api.post("/powerhour/sessions/\(id)/start/", token: token)
    }

    func pauseSession(id: String, token: String) async throws -> SessionState {
        try await api.post("/powerhour/sessions/\(id)/pause/", token: token)
    }

    func resumeSession(id: String, token: String) async throws -> SessionState {
        try await api.post("/powerhour/sessions/\(id)/resume/", token: token)
    }

    func endSession(id: String, token: String) async throws -> SessionState {
        try await api.post("/powerhour/sessions/\(id)/end/", token: token)
    }

    func nextTrack(id: String, token: String) async throws -> SessionState {
        try await api.post("/powerhour/sessions/\(id)/next/", token: token)
    }

    func getState(id: String, token: String) async throws -> SessionState {
        try await api.get("/powerhour/sessions/\(id)/state/", token: token)
    }

    func addTrack(sessionId: String, trackId: Int, startOffsetMs: Int = 0, token: String) async throws -> SessionTrackItem {
        let body = AddTrackRequest(trackId: trackId, startOffsetMs: startOffsetMs)
        return try await api.post("/powerhour/sessions/\(sessionId)/tracks/", body: body, token: token)
    }

    func removeTrack(sessionId: String, trackId: String, token: String) async throws {
        try await api.delete("/powerhour/sessions/\(sessionId)/tracks/\(trackId)/", token: token)
    }
}
