import SwiftUI

/// Hosts the current section and runs the prototype's navigation motion:
/// the old section fades up and out (200 ms, ease-in), then the new one rises
/// in from below (480 ms, `cubic-bezier(.2,.8,.2,1)`). Reduce Motion swaps
/// sections immediately.
///
/// It follows `selection` (normally `AppModel.section`), so any code that
/// changes the section gets the transition.
struct SectionStage<Content: View>: View {
    private enum Phase { case shown, leaving, entering }

    let selection: JukeSection
    @ViewBuilder var content: (JukeSection) -> Content

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var displayed: JukeSection?
    @State private var phase: Phase = .shown
    @State private var generation = 0

    var body: some View {
        let section = displayed ?? selection
        content(section)
            .id(section)
            .opacity(phase == .shown ? 1 : 0)
            .offset(y: offset)
            .scaleEffect(scale)
            .onChange(of: selection) { _, target in transition(to: target) }
    }

    private var offset: CGFloat {
        switch phase {
        case .shown: 0
        case .leaving: JukeMotion.Stage.outOffset
        case .entering: JukeMotion.Stage.inOffset
        }
    }

    private var scale: CGFloat {
        switch phase {
        case .shown: 1
        case .leaving: JukeMotion.Stage.outScale
        case .entering: JukeMotion.Stage.inScale
        }
    }

    private func transition(to target: JukeSection) {
        generation += 1
        let current = generation
        guard let outAnimation = JukeMotion.navigationOut(reduceMotion: reduceMotion) else {
            displayed = target
            phase = .shown
            return
        }
        withAnimation(outAnimation) {
            phase = .leaving
        } completion: {
            guard current == generation else { return }
            var instant = Transaction()
            instant.disablesAnimations = true
            withTransaction(instant) {
                displayed = target
                phase = .entering
            }
            Task { @MainActor in
                guard current == generation else { return }
                withAnimation(JukeMotion.navigationIn(reduceMotion: reduceMotion)) { phase = .shown }
            }
        }
    }
}
