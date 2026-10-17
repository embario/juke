import Foundation

/// How records move when flipping through the Library crate.
enum CrateFlipDirection: String, CaseIterable, Identifiable, Sendable {
    case sideToSide, frontToBack

    var id: String { rawValue }

    var label: String {
        switch self {
        case .sideToSide: "Side to side"
        case .frontToBack: "Front to back"
        }
    }
}
