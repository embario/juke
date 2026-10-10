import SwiftUI

/// The radio tuner in a drawer at the bottom of Now Playing: a handle that names the tuned station
/// (always visible, above the tab bar) and, opened, the FM dial. Tap the handle or drag it up to
/// open, tap or drag down to close. Nothing about it is remembered: it starts closed.
struct TunerDrawer: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Binding var expanded: Bool
    /// Reset by SwiftUI when the system cancels a drag.
    @GestureState private var dragY: CGFloat = 0
    @ScaledMetric(relativeTo: .body) private var handleHeight = TunerDrawerStyle.handleHeight
    /// The dial itself keeps its size; only the two-line readout under it grows with the text.
    @ScaledMetric(relativeTo: .footnote) private var readoutHeight = TunerDrawerStyle.readoutHeight
    private var dialHeight: CGFloat { TunerDrawerStyle.dialBase + readoutHeight }

    private var motion: Animation { reduceMotion ? .easeInOut(duration: 0.15) : .smooth(duration: 0.35) }

    var body: some View {
        let progress = TunerDrawerGesture.progress(expanded: expanded, translation: dragY, travel: dialHeight)
        VStack(spacing: 0) {
            handle
            FMDialView()
                .padding(.horizontal, 16).padding(.bottom, 14)
                .frame(height: dialHeight, alignment: .top)
                .frame(height: dialHeight * progress, alignment: .top)
                .clipped()
                .opacity(progress)
                .allowsHitTesting(expanded)
                .accessibilityHidden(!expanded)
        }
        .frame(maxWidth: .infinity)
        .background {
            RoundedRectangle(cornerRadius: 24, style: .continuous).fill(.regularMaterial)
                .shadow(color: .black.opacity(0.2), radius: 12, y: -2)
        }
        .padding(.horizontal, 12)
        .animation(dragY == 0 ? motion : nil, value: expanded)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("radio.tuner.drawer")
    }

    private var handle: some View {
        VStack(spacing: 4) {
            Capsule().fill(.secondary.opacity(0.5)).frame(width: 36, height: 5).padding(.top, 8)
            HStack(spacing: 8) {
                Image(systemName: "dot.radiowaves.left.and.right")
                Text(readout).font(.subheadline.weight(.semibold)).lineLimit(1)
                Spacer(minLength: 0)
                Image(systemName: "chevron.up").font(.caption.weight(.bold)).rotationEffect(.degrees(expanded ? 180 : 0))
            }
            .padding(.horizontal, 18)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, minHeight: handleHeight, maxHeight: handleHeight)
        .contentShape(Rectangle())
        .foregroundStyle(.primary)
        // A tap toggles; a drag follows the finger. (Not a Button, whose own gesture would swallow the drag.)
        .onTapGesture { withAnimation(motion) { expanded.toggle() } }
        .gesture(
            DragGesture(minimumDistance: 10, coordinateSpace: .global)  // the handle moves under the finger, so measure on screen
                .updating($dragY) { value, state, _ in state = value.translation.height }
                .onEnded { value in
                    let next = TunerDrawerGesture.settles(expanded: expanded, translation: value.translation.height,
                                                          velocity: value.velocity.height, travel: dialHeight)
                    if next != expanded { withAnimation(motion) { expanded = next } }
                }
        )
        .accessibilityElement(children: .ignore)
        .accessibilityAddTraits(.isButton)
        .accessibilityLabel(expanded ? "Tuner, open" : "Tuner, closed")
        .accessibilityValue(readout)
        .accessibilityHint(expanded ? "Closes the tuner." : "Opens the tuner to change station.")
        .accessibilityAction { withAnimation(motion) { expanded.toggle() } }
        .accessibilityIdentifier("radio.tuner.handle")
    }

    private var readout: String {
        guard let tuned = model.radio.tunedStation else { return "Tuner" }
        return "\(tuned.name) · FM \(tuned.frequencyLabel)"
    }
}

enum TunerDrawerStyle {
    /// The handle's height: the part that is always on screen.
    static let handleHeight: CGFloat = 52
    /// The dial and its padding, shown when open, and the readout line under it.
    static let dialBase: CGFloat = 112
    static let readoutHeight: CGFloat = 26
    /// Space kept under the card's content so the closed handle never covers it.
    static let reserve: CGFloat = handleHeight + 8
}
