import Foundation

/// The rules behind the memory detail screen, kept out of the view so they can be tested.
enum MemoryDetailLogic {
    /// The description to save, or nil when nothing changed (ignoring surrounding whitespace).
    static func descriptionChange(from old: String, to new: String) -> String? {
        let trimmed = new.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed == old.trimmingCharacters(in: .whitespacesAndNewlines) ? nil : trimmed
    }

    /// Tags worth offering with one tap: what the classifier suggested, then the listener's own vocabulary,
    /// minus anything the memory already has (case-insensitive), without repeats.
    static func suggestedTags(for memory: MusicMemory, vocabulary: [String], limit: Int = 12) -> [String] {
        var seen = Set(memory.tags.map { $0.lowercased() })
        var result: [String] = []
        for tag in memory.generatedTags + vocabulary {
            let key = tag.lowercased()
            guard !tag.trimmingCharacters(in: .whitespaces).isEmpty, seen.insert(key).inserted else { continue }
            result.append(tag)
            if result.count == limit { break }
        }
        return result
    }

    /// Photos and videos, in the order they were attached. Anything that is not a video is shown as a photo.
    static func photos(_ memory: MusicMemory) -> [MemoryMedia] { memory.media.filter { $0.kind != "video" } }
    static func videos(_ memory: MusicMemory) -> [MemoryMedia] { memory.media.filter { $0.kind == "video" } }

    /// The server rejects a memory with no description, songs or attachments; stop before asking.
    static func canRemove(_ media: MemoryMedia, from memory: MusicMemory) -> Bool {
        let others = memory.media.contains { $0.id != media.id }
        let hasText = !memory.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return others || hasText || !memory.songs.isEmpty
    }

    /// What a "who and where" line shows under the title.
    static func context(_ memory: MusicMemory) -> String {
        var parts = [memory.occurredAt.formatted(date: .long, time: .omitted)]
        if !memory.place.isEmpty { parts.append(memory.place) }
        return parts.joined(separator: " · ")
    }

    /// A short summary used as the section footer for attachments.
    static func mediaSummary(_ memory: MusicMemory) -> String {
        let photos = Self.photos(memory).count, videos = Self.videos(memory).count
        var parts: [String] = []
        if photos > 0 { parts.append(photos == 1 ? "1 photo" : "\(photos) photos") }
        if videos > 0 { parts.append(videos == 1 ? "1 video" : "\(videos) videos") }
        return parts.isEmpty ? "No photos or videos yet" : parts.joined(separator: " · ")
    }
}
