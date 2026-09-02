import Foundation
#if canImport(FoundationModels)
import FoundationModels
#endif

actor LocalVibeIntelligence {
    func openingQuestion(currentTrack: String?, recentConversation: [String]) async throws -> String {
        #if canImport(FoundationModels)
        if #available(macOS 26.0, *) {
            let model = SystemLanguageModel.default
            guard case .available = model.availability else { throw LocalVibeError.unavailable }
            let session = LanguageModelSession(instructions: "Write one thoughtful, unintrusive question for a music listener. It should feel specific and inviting, avoid therapy language, and never request sensitive personal details.")
            let history = recentConversation.suffix(8).joined(separator: "\n")
            let response = try await session.respond(to: "Current music: \(currentTrack ?? "none")\nPrivate local conversation context:\n\(history)")
            return response.content
        }
        #endif
        throw LocalVibeError.unavailable
    }

    func respond(message: String, currentTrack: String?, recentConversation: [String]) async throws -> String {
        #if canImport(FoundationModels)
        if #available(macOS 26.0, *) {
            let model = SystemLanguageModel.default
            guard case .available = model.availability else { throw LocalVibeError.unavailable }
            let session = LanguageModelSession(instructions: "You are Juke Vibe, a perceptive music companion. Be concise, curious, specific, and never invent music facts. Do not solicit sensitive personal information.")
            let history = recentConversation.suffix(8).joined(separator: "\n")
            let track = currentTrack ?? "Nothing is currently playing"
            let response = try await session.respond(to: "Current music: \(track)\nRecent private local conversation:\n\(history)\nListener: \(message)")
            return response.content
        }
        #endif
        throw LocalVibeError.unavailable
    }
}

enum LocalVibeError: LocalizedError {
    case unavailable
    var errorDescription: String? { "On-device intelligence is not available on this Mac. Enable cloud chat in your Juke account to continue." }
}
