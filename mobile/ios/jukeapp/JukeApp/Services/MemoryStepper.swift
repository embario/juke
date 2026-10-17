import Foundation

/// Chronological order of memories: by when they happened, oldest first.
enum MemoryChronology {
    static func ordered(_ memories: [MusicMemory]) -> [MusicMemory] {
        memories.sorted {
            if $0.occurredAt != $1.occurredAt { return $0.occurredAt < $1.occurredAt }
            if $0.createdAt != $1.createdAt { return $0.createdAt < $1.createdAt }
            return $0.id.uuidString < $1.id.uuidString
        }
    }

    /// The song a memory plays: its first one with something to play.
    static func playableSong(_ memory: MusicMemory) -> MemorySong? {
        memory.songs.first { $0.providerID != nil || $0.playbackURL != nil }
    }

    /// The nearest later (`direction` 1) or earlier (-1) memory that has a playable song.
    static func step(from id: UUID, direction: Int, in memories: [MusicMemory]) -> MusicMemory? {
        let list = ordered(memories)
        guard let index = list.firstIndex(where: { $0.id == id }) else { return nil }
        let candidates = direction >= 0 ? Array(list[(index + 1)...]) : Array(list[..<index].reversed())
        return candidates.first { playableSong($0) != nil }
    }
}

/// What the persistent player needs to step through memories.
@MainActor
protocol TransportMemory: AnyObject {
    /// True while a memory's song is what the listener is hearing.
    var isActive: Bool { get }
    /// Plays the neighbouring memory; false when there is none in that direction.
    func step(_ direction: Int) async -> Bool
}

/// Steps from the memory that is playing to the next (or previous) one in time.
@MainActor
final class MemoryStepper: TransportMemory {
    /// Right after a memory starts the observer may still report the previous song.
    static let startGrace: TimeInterval = 15

    private let player: MemoryPlayer
    private let memories: @MainActor () -> [MusicMemory]
    private let track: @MainActor () -> NowPlayingTrack?
    private let now: @MainActor () -> Date

    init(player: MemoryPlayer, memories: @escaping @MainActor () -> [MusicMemory], track: @escaping @MainActor () -> NowPlayingTrack?,
         now: @escaping @MainActor () -> Date = { .now }) {
        self.player = player; self.memories = memories; self.track = track; self.now = now
    }

    static func matches(_ song: MemorySong, _ track: NowPlayingTrack) -> Bool {
        if let id = song.providerID, id == track.id { return true }
        return song.title.trimmingCharacters(in: .whitespaces).caseInsensitiveCompare(track.title.trimmingCharacters(in: .whitespaces)) == .orderedSame
    }

    private var playing: (memory: MusicMemory, song: MemorySong)? {
        guard let context = player.current, let memory = memories().first(where: { $0.id == context.memoryID }),
              let song = memory.songs.first(where: { $0.id == context.songID }) else { return nil }
        return (memory, song)
    }

    var isActive: Bool {
        guard let context = player.current, let playing else { return false }
        if now().timeIntervalSince(context.startedAt) < Self.startGrace { return true }
        guard let track = track() else { return false }
        return Self.matches(playing.song, track)
    }

    func step(_ direction: Int) async -> Bool {
        guard let playing, let next = MemoryChronology.step(from: playing.memory.id, direction: direction, in: memories()),
              let song = MemoryChronology.playableSong(next) else { return false }
        await player.play(song, in: next.id)
        return true
    }
}
