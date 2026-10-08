/// The iPhone tab bar: the four Mac sections plus Settings. New Station is
/// reached from Radio and Library (it is a route inside Radio, as on the Mac).
enum JukeTab: String, CaseIterable, Identifiable, Sendable {
    case radio, library, memories, chat, settings

    var id: String { rawValue }

    var title: String {
        switch self {
        case .radio: "Radio"
        case .library: "Library"
        case .memories: "Memories"
        case .chat: "Chat"
        case .settings: "Settings"
        }
    }

    var symbol: String {
        switch self {
        case .radio: "dot.radiowaves.left.and.right"
        case .library: "square.stack"
        case .memories: "photo.on.rectangle.angled"
        case .chat: "bubble.left.and.bubble.right"
        case .settings: "gearshape"
        }
    }

    /// Radio is the player itself, and Chat owns the bottom edge for its composer.
    var showsMiniPlayer: Bool { self != .radio && self != .chat }
}
