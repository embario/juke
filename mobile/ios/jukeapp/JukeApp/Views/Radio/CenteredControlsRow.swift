import SwiftUI

/// The geometry of a row whose middle stays exactly in the middle of the screen, whatever sits on
/// either side of it. Kept apart from the layout so it can be tested.
enum ControlsCentering {
    /// The width each side may take: half of what the centred controls leave over, less the gap.
    static func sideWidth(container: CGFloat, center: CGFloat, gap: CGFloat) -> CGFloat {
        guard container.isFinite else { return .infinity }
        return max(0, (container - center) / 2 - gap)
    }

    /// Where the centred controls start: always the middle, never moved by the sides.
    static func centerX(container: CGFloat, center: CGFloat) -> CGFloat {
        ((container - center) / 2).rounded()
    }
}

/// Three views in a row: `leading` hugs the left edge, `trailing` the right edge, and `center` sits
/// in the middle of the available width. Unlike an `HStack` with spacers, a wide leading view
/// cannot push the centred controls off-centre; it is the leading view that gives way (it is
/// proposed only the room beside the controls).
struct CenteredControlsRow<Leading: View, Center: View, Trailing: View>: View {
    var gap: CGFloat = 8
    @ViewBuilder var leading: Leading
    @ViewBuilder var center: Center
    @ViewBuilder var trailing: Trailing

    var body: some View {
        CenteredControlsLayout(gap: gap) {
            leading
            center
            trailing
        }
    }
}

extension CenteredControlsRow where Trailing == Color {
    init(gap: CGFloat = 8, @ViewBuilder leading: () -> Leading, @ViewBuilder center: () -> Center) {
        self.init(gap: gap, leading: leading, center: center, trailing: { Color.clear })
    }
}

private struct CenteredControlsLayout: Layout {
    var gap: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard subviews.count == 3 else { return .zero }
        let center = subviews[1].sizeThatFits(.unspecified)
        let width = proposal.width ?? 0
        let side = ControlsCentering.sideWidth(container: width, center: center.width, gap: gap)
        let leading = subviews[0].sizeThatFits(ProposedViewSize(width: side, height: proposal.height))
        let trailing = subviews[2].sizeThatFits(ProposedViewSize(width: side, height: proposal.height))
        return CGSize(width: width, height: max(center.height, leading.height, trailing.height))
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard subviews.count == 3 else { return }
        let center = subviews[1].sizeThatFits(.unspecified)
        let side = ControlsCentering.sideWidth(container: bounds.width, center: center.width, gap: gap)
        // Whole points, so a 44 pt control stays 44 pt tall rather than 43.99.
        func top(_ height: CGFloat) -> CGFloat { bounds.minY + ((bounds.height - height) / 2).rounded() }
        subviews[1].place(at: CGPoint(x: bounds.minX + ControlsCentering.centerX(container: bounds.width, center: center.width), y: top(center.height)),
                          anchor: .topLeading, proposal: ProposedViewSize(center))
        let leading = subviews[0].sizeThatFits(ProposedViewSize(width: side, height: bounds.height))
        let leadingWidth = min(leading.width, side)
        subviews[0].place(at: CGPoint(x: bounds.minX, y: top(leading.height)), anchor: .topLeading,
                          proposal: ProposedViewSize(width: leadingWidth, height: leading.height))
        let trailing = subviews[2].sizeThatFits(ProposedViewSize(width: side, height: bounds.height))
        let trailingWidth = min(trailing.width, side)
        subviews[2].place(at: CGPoint(x: bounds.maxX - trailingWidth, y: top(trailing.height)), anchor: .topLeading,
                          proposal: ProposedViewSize(width: trailingWidth, height: trailing.height))
    }
}
