import CoreGraphics

/// Sizes the Radio card to the room above the tab bar and between the screen's edges: the sleeve
/// and record are as large as both allow. The tuner lives in a bottom drawer, so it takes no room
/// from them beyond the drawer's collapsed handle.
enum RadioLayout {
    static let maxSleeve: CGFloat = 260
    static let minSleeve: CGFloat = 140
    /// Height of everything on the card except the sleeve (header, titles, scrubber, transport,
    /// reactions, the collapsed drawer's reserve and padding), measured at the default text size.
    static let fixedContentHeight: CGFloat = 445
    /// The record slides out by half the sleeve, so its label stays grabbable.
    static let discOffsetRatio: CGFloat = 0.5
    /// Side margin of the sleeve row, a little tighter than the card's 20 pt so the vinyl can be large.
    static let rowMargin: CGFloat = 12

    /// The sleeve (and record) side for the room that is left; `containerWidth` is the card's full width.
    static func sleeveSide(visibleHeight: CGFloat, containerWidth: CGFloat = .infinity) -> CGFloat {
        let byHeight = visibleHeight.isFinite ? visibleHeight - fixedContentHeight : maxSleeve
        // The sleeve plus the record peeking out of it must fit between the margins.
        let byWidth = containerWidth.isFinite ? (containerWidth - 2 * rowMargin) / (1 + discOffsetRatio) : maxSleeve
        return min(maxSleeve, max(minSleeve, min(byHeight, byWidth.rounded(.down))))
    }

    static func discOffset(side: CGFloat) -> CGFloat { (side * discOffsetRatio).rounded() }
}

/// The tuner's bottom drawer: a handle that opens on a tap or an upward drag, closes on a tap or a
/// downward drag. The maths is kept apart from the view so it can be tested.
enum TunerDrawerGesture {
    /// A slow drag must pass this share of the way before it is kept.
    static let commitFraction = 0.4
    /// A flick faster than this (points per second) decides by its direction.
    static let flingVelocity: CGFloat = 500

    /// How open the drawer is (0 closed, 1 open) while the finger is down; up is negative translation.
    static func progress(expanded: Bool, translation: CGFloat, travel: CGFloat) -> Double {
        guard travel > 0 else { return expanded ? 1 : 0 }
        return min(1, max(0, (expanded ? 1 : 0) - Double(translation / travel)))
    }

    /// Whether the drawer is open when the finger lifts. Letting go early returns it to where it began.
    static func settles(expanded: Bool, translation: CGFloat, velocity: CGFloat, travel: CGFloat) -> Bool {
        if abs(velocity) >= flingVelocity { return velocity < 0 }
        let at = progress(expanded: expanded, translation: translation, travel: travel)
        return expanded ? at > 1 - commitFraction : at > commitFraction
    }
}
