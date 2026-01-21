import Foundation

enum SessionStatus: String, Codable {
    case lobby, active, paused, ended
}

struct PowerHourSession: Codable, Identifiable {
    let id: String
    let admin: Int
    let title: String
    let inviteCode: String

    // Configuration
    let tracksPerPlayer: Int
    let maxTracks: Int
    let secondsPerTrack: Int
    let transitionClip: String
    let hideTrackOwners: Bool

    // State
    let status: SessionStatus
    let currentTrackIndex: Int

    let createdAt: String
    let startedAt: String?
    let endedAt: String?

    // Included in list responses
    let playerCount: Int?
    let trackCount: Int?

    var isActive: Bool {
        status == .active || status == .paused
    }

    var statusLabel: String {
        switch status {
        case .lobby: return "Lobby"
        case .active: return "Playing"
        case .paused: return "Paused"
        case .ended: return "Ended"
        }
    }
}

struct CreateSessionRequest: Encodable {
    let title: String
    let tracksPerPlayer: Int
    let maxTracks: Int
    let secondsPerTrack: Int
    let transitionClip: String
    let hideTrackOwners: Bool
}

struct JoinSessionRequest: Encodable {
    let inviteCode: String
}
