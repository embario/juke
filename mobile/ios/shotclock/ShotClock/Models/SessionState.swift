import Foundation

struct SessionState: Decodable {
    let status: SessionStatus
    let currentTrackIndex: Int
    let startedAt: String?
    let playerCount: Int
    let trackCount: Int
}
