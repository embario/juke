import CoreGraphics

/// How far the record travels between "out" and "in the sleeve", and when a drag
/// of its label commits. Pure so the thresholds can be tested.
enum VinylSleeve {
    /// Share of the travel the finger must cover (or the fling must project to) to commit.
    static let commitFraction: CGFloat = 0.45
    static let flingFraction: CGFloat = 0.8
    /// How far past either end the record may be dragged (rubber-band allowance).
    static let overshoot: CGFloat = 14

    /// The record sits almost fully behind the sleeve when put away, a sliver peeking out.
    static func putAwayOffset(side: CGFloat) -> CGFloat { (side * 0.18).rounded() }

    static func travel(out: CGFloat, side: CGFloat) -> CGFloat { max(1, out - putAwayOffset(side: side)) }

    /// A drag is a label slide (not a seek) when the record is put away, because its label is
    /// hidden under the sleeve and only the rim shows, or when the finger lands on the label.
    static func grabsLabel(putAway: Bool, onLabel: Bool) -> Bool { putAway || onLabel }

    /// Finger translation to record offset: it follows the finger and resists past the ends.
    static func offset(forTranslation dx: CGFloat, putAway: Bool, travel: CGFloat) -> CGFloat {
        let range: ClosedRange<CGFloat> = putAway ? (-overshoot)...(travel + overshoot) : (-(travel + overshoot))...overshoot
        return min(range.upperBound, max(range.lowerBound, dx))
    }

    static func outcome(translation: CGFloat, predicted: CGFloat, putAway: Bool, travel: CGFloat) -> VinylLabelSlide.Outcome {
        if putAway {
            return translation > travel * commitFraction || predicted > travel * flingFraction ? .resume : .none
        }
        return translation < -travel * commitFraction || predicted < -travel * flingFraction ? .putAway : .none
    }
}
