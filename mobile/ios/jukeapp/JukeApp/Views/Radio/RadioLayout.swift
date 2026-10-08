import CoreGraphics

/// Sizes the Radio card to the room above the tab bar so the FM tuner is never
/// cut off on smaller phones; only the sleeve gives way.
enum RadioLayout {
    static let maxSleeve: CGFloat = 196
    static let minSleeve: CGFloat = 120
    /// Height of everything on the card except the sleeve (header, titles, scrubber,
    /// transport, reactions, dial, caption and padding), measured at the default text size.
    static let fixedContentHeight: CGFloat = 440

    static func sleeveSide(visibleHeight: CGFloat) -> CGFloat {
        guard visibleHeight.isFinite else { return maxSleeve }
        return min(maxSleeve, max(minSleeve, visibleHeight - fixedContentHeight))
    }

    /// The record slides out by two thirds of the sleeve, so its label stays grabbable.
    static func discOffset(side: CGFloat) -> CGFloat { (side * 130 / maxSleeve).rounded() }
}
