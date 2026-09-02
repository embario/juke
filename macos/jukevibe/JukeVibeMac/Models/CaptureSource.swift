import Foundation

enum CaptureSource: String, CaseIterable, Codable, Identifiable {
    case systemAudio
    case microphone
    case playerMetadata

    static let audioChoices: [CaptureSource] = [.systemAudio, .microphone]

    var id: String { rawValue }

    var label: String {
        switch self {
        case .systemAudio: "This Mac"
        case .microphone: "Around Me"
        case .playerMetadata: "Player metadata"
        }
    }

    var detail: String {
        switch self {
        case .systemAudio: "Spotify, Apple Music, browser, or Juke Player"
        case .microphone: "Radio, speakers, venues, or other outside sources"
        case .playerMetadata: "Apple Music or Spotify, without recording audio"
        }
    }

    var symbol: String {
        switch self {
        case .systemAudio: "macbook.and.iphone"
        case .microphone: "mic.fill"
        case .playerMetadata: "music.note.list"
        }
    }
}
