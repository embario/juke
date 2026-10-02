import Foundation
import FoundationModels

actor LocalVibeIntelligence {
    func respond(_ message: String, track: String?, history: [String]) async throws -> String {
        guard case .available = SystemLanguageModel.default.availability else { throw CocoaError(.featureUnsupported) }
        let session = LanguageModelSession(instructions: "You are Juke, a concise, perceptive music companion. Be curious and specific. Never invent facts or solicit sensitive personal information.")
        let reply = try await session.respond(to: "Current music: \(track ?? "none")\nPrivate on-device context:\n\(history.suffix(8).joined(separator: "\n"))\nListener: \(message)")
        return reply.content
    }

    func question(track: String?, history: [String]) async throws -> String {
        guard case .available = SystemLanguageModel.default.availability else { throw CocoaError(.featureUnsupported) }
        let session = LanguageModelSession(instructions: "Write one thoughtful, unintrusive question for a music listener. Avoid therapy language and sensitive personal questions.")
        return try await session.respond(to: "Current music: \(track ?? "none")\nPrivate local history:\n\(history.suffix(8).joined(separator: "\n"))").content
    }
}
