import SwiftUI

/// The maths of the pull-down reveal, kept apart from the view so it can be tested.
enum DetailRevealGesture {
    /// A slow drag must pass this share of the way before it is kept.
    static let commitFraction = 0.35
    /// A flick faster than this (points per second) decides the outcome by its direction.
    static let flingVelocity: CGFloat = 600

    /// How far the details have come down (0 hidden, 1 fully shown) while the finger is down.
    static func progress(revealed: Bool, translation: CGFloat, travel: CGFloat) -> Double {
        guard travel > 0 else { return revealed ? 1 : 0 }
        return min(1, max(0, (revealed ? 1 : 0) + Double(translation / travel)))
    }

    /// Whether the details stay shown when the finger lifts. A drag that is let go before the
    /// commit point goes back to where it started, which is how a gesture is cancelled.
    static func settles(revealed: Bool, translation: CGFloat, velocity: CGFloat, travel: CGFloat) -> Bool {
        if abs(velocity) >= flingVelocity { return velocity > 0 }
        let at = progress(revealed: revealed, translation: translation, travel: travel)
        return revealed ? at > 1 - commitFraction : at > commitFraction
    }

    /// Only a mostly vertical drag moves the details; a sideways one is left to scrolling and paging.
    static func isVertical(_ translation: CGSize) -> Bool {
        abs(translation.height) > abs(translation.width)
    }
}

/// A pane with details tucked above it. Pulling the pane's header down brings the details down
/// over it with the finger; pushing up (or tapping the button) sends them back. Reused by the
/// artist and the album screens.
struct DetailReveal<Hero: View, Content: View, Details: View>: View {
    @Binding var revealed: Bool
    let showLabel: String
    let hideLabel: String
    /// Prefix of the accessibility identifiers: `<prefix>.reveal`, `.hide` and `.details`.
    let idPrefix: String
    @ViewBuilder var hero: Hero
    @ViewBuilder var content: Content
    @ViewBuilder var details: Details

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    /// Reset by SwiftUI when the system cancels a drag.
    @GestureState private var heroDrag = DragTrack()
    @GestureState private var panelDrag = DragTrack()
    @State private var panelAtBottom = true

    private struct DragTrack {
        var begun = false
        var eligible = false
        var dy: CGFloat = 0
    }

    private var motion: Animation { reduceMotion ? .easeInOut(duration: 0.15) : .smooth(duration: 0.4) }

    var body: some View {
        GeometryReader { geometry in
            let travel = geometry.size.height
            let dragging = heroDrag.dy != 0 || panelDrag.dy != 0
            let progress = DetailRevealGesture.progress(revealed: revealed, translation: heroDrag.dy + panelDrag.dy, travel: travel)
            ZStack(alignment: .top) {
                pane(travel: travel)
                    .overlay { Color.black.opacity(0.22 * progress).allowsHitTesting(false) }
                    .disabled(revealed).accessibilityHidden(revealed)
                panel(travel: travel)
                    .offset(y: reduceMotion ? 0 : -travel * (1 - progress))
                    .opacity(reduceMotion ? progress : 1)
                    .allowsHitTesting(revealed)
                    .accessibilityHidden(!revealed)
            }
            .frame(width: geometry.size.width, height: travel)
            .clipped()
            .animation(dragging ? nil : motion, value: progress)
        }
        .sensoryFeedback(.impact(weight: .light), trigger: revealed)
    }

    // MARK: Pane

    private func pane(travel: CGFloat) -> some View {
        VStack(spacing: 0) {
            VStack(spacing: 6) {
                hero
                Button { setRevealed(true) } label: {
                    Label(showLabel, systemImage: "chevron.down").font(.footnote.weight(.semibold))
                        .frame(maxWidth: .infinity, minHeight: 44)
                }
                .buttonStyle(.plain).foregroundStyle(.secondary)
                .accessibilityHint("You can also swipe down on the top of this screen.")
                .accessibilityIdentifier("\(idPrefix).reveal")
            }
            .contentShape(Rectangle())
            .simultaneousGesture(revealGesture(travel: travel))
            .accessibilityAction(named: showLabel) { setRevealed(true) }
            content
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    private func revealGesture(travel: CGFloat) -> some Gesture {
        DragGesture(minimumDistance: 12)
            .updating($heroDrag) { value, track, _ in
                if !track.begun {
                    track.begun = true
                    track.eligible = !revealed && DetailRevealGesture.isVertical(value.translation) && value.translation.height > 0
                }
                track.dy = track.eligible ? value.translation.height : 0
            }
            .onEnded { value in
                guard !revealed, DetailRevealGesture.isVertical(value.translation) else { return }
                setRevealed(DetailRevealGesture.settles(revealed: false, translation: value.translation.height,
                                                        velocity: value.velocity.height, travel: travel))
            }
    }

    // MARK: Details

    private func panel(travel: CGFloat) -> some View {
        VStack(spacing: 0) {
            // At the top, where the panel meets the pane, so nothing (the mini player, the tab bar) can cover it.
            Button { setRevealed(false) } label: {
                HStack(spacing: 6) {
                    Image(systemName: "chevron.up")
                    Text(hideLabel)
                }
                .font(.footnote.weight(.semibold)).foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, minHeight: 44)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .simultaneousGesture(hideGesture(travel: travel, needsBottom: false))
            .accessibilityHint("You can also swipe up.")
            .accessibilityIdentifier("\(idPrefix).hide")
            ScrollView {
                details.frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 16).padding(.top, 4).padding(.bottom, 16)
            }
            .onScrollGeometryChange(for: Bool.self) { $0.contentOffset.y + $0.containerSize.height >= $0.contentSize.height - 1 } action: { _, atBottom in
                panelAtBottom = atBottom
            }
            .simultaneousGesture(hideGesture(travel: travel, needsBottom: true))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background {
            // The shadow belongs to the panel's surface, not to the text drawn on it.
            UnevenRoundedRectangle(bottomLeadingRadius: 24, bottomTrailingRadius: 24, style: .continuous)
                .fill(.regularMaterial)
                .shadow(color: .black.opacity(0.25), radius: 14, y: 6)
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("\(idPrefix).details")
        .accessibilityAction(.escape) { setRevealed(false) }
    }

    /// An upward push on the details. Inside the scrolling list it only counts once the list is at
    /// its end when the push starts, so reading a long list is never mistaken for dismissing it.
    private func hideGesture(travel: CGFloat, needsBottom: Bool) -> some Gesture {
        DragGesture(minimumDistance: 12)
            .updating($panelDrag) { value, track, _ in
                if !track.begun {
                    track.begun = true
                    track.eligible = revealed && DetailRevealGesture.isVertical(value.translation) && value.translation.height < 0
                        && (!needsBottom || panelAtBottom)
                }
                track.dy = track.eligible ? value.translation.height : 0
            }
            .onEnded { value in
                guard revealed, DetailRevealGesture.isVertical(value.translation), value.translation.height < 0,
                      !needsBottom || panelAtBottom else { return }
                setRevealed(DetailRevealGesture.settles(revealed: true, translation: value.translation.height,
                                                        velocity: value.velocity.height, travel: travel))
            }
    }

    private func setRevealed(_ next: Bool) {
        guard next != revealed else { return }
        withAnimation(motion) { revealed = next }
    }
}
