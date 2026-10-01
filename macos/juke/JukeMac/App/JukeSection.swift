/// The four top-level sections in the header's segmented nav.
///
/// Each section's screen lives in its own folder under `Views/`
/// (`Views/Radio/RadioScreen.swift`, `Views/Library/LibraryScreen.swift`,
/// `Views/Memories/MemoriesScreen.swift`, `Views/Chat/ChatScreen.swift`).
enum JukeSection: String, CaseIterable, Identifiable, Sendable {
    case radio, library, memories, chat

    var id: String { rawValue }

    var title: String {
        switch self {
        case .radio: "Radio"
        case .library: "Library"
        case .memories: "Memories"
        case .chat: "Chat"
        }
    }

    /// Keyboard shortcut digit (Command-1 … Command-4).
    var shortcut: Character {
        switch self {
        case .radio: "1"
        case .library: "2"
        case .memories: "3"
        case .chat: "4"
        }
    }

    /// Whether the floating mini now-playing pill shows on this section.
    var showsMiniPlayer: Bool { self != .radio }
}
