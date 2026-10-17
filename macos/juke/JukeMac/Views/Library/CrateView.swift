import AppKit
import SwiftUI

/// A crate of records drawn as album-art sleeves.
///
/// - Side to side (coverflow) or front to back (a bin), per `mode`.
/// - Drag along the axis with momentum, scroll or swipe to step, click a side
///   record to bring it forward, click the front record to pull it
///   (`onActivateFront`, New Station only).
/// - Keyboard: ←/→ (↑/↓ also work, natural in the bin) move focus, Return pulls.
/// - VoiceOver: one adjustable element whose value is the record in front.
///
/// Motion follows the prototype: a 560 ms soft ease when settling, no
/// animation while the pointer is down, brightness falling off with depth.
struct CrateView: View {
    let items: [Radio.CrateItem]
    @Binding var focus: Int
    var mode: CrateMode
    /// Seed ids (`Radio.Seed.id`) that show the pulled check badge.
    var pulledIDs: Set<String> = []
    /// Click on the front record or Return. `nil` in the Library.
    var onActivateFront: ((Radio.CrateItem) -> Void)?
    /// VoiceOver name for `onActivateFront` ("Pull this record").
    var activateLabel: (Radio.CrateItem) -> String = { _ in "Pull this record" }
    /// Return on the front record. Defaults to `onActivateFront`; the Library
    /// uses it to start radio (a click there only focuses).
    var onReturn: ((Radio.CrateItem) -> Void)?

    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var dragDelta: CGFloat = 0
    @State private var isDragging = false
    /// Set while a drag moves so the click that ends it is not treated as a tap.
    @State private var suppressTap = false
    @State private var wheel = CrateWheelAccumulator()
    @State private var wheelMonitor = ScrollWheelMonitor()
    @FocusState private var hasKeyboardFocus: Bool

    private var position: CGFloat { CrateLayout.position(focus: focus, dragDelta: dragDelta, mode: mode) }

    private var settle: Animation? {
        reduceMotion ? nil : JukeMotion.easeOutSoft(CrateLayout.settleDuration)
    }

    var body: some View {
        ZStack(alignment: .top) {
            // Keyed by record, so a sleeve keeps its identity (and animates) when
            // the list around it changes.
            ForEach(CrateLayout.visibleIndices(focus: focus, count: items.count).map { VisibleSleeve(index: $0, id: items[$0].id) }) { visible in
                sleeve(at: visible.index)
            }
        }
        .frame(maxWidth: .infinity, minHeight: CrateLayout.wellHeight, maxHeight: CrateLayout.wellHeight, alignment: .top)
        .background(theme.well.color)
        .clipShape(RoundedRectangle(cornerRadius: JukeRadius.well, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: JukeRadius.well, style: .continuous)
                .strokeBorder(theme.accent.color.opacity(hasKeyboardFocus ? 0.8 : 0), lineWidth: 2)
        }
        .contentShape(Rectangle())
        .simultaneousGesture(drag)
        .onHover { inside in
            // Installed once on entering, removed on leaving.
            if inside { startWheel() } else { wheelMonitor.stop() }
        }
        .onChange(of: mode) { _, _ in if wheelMonitor.isActive { startWheel() } }
        .onChange(of: items.count) { _, _ in if wheelMonitor.isActive { startWheel() } }
        .onDisappear { wheelMonitor.stop() }
        .focusable()
        .focused($hasKeyboardFocus)
        .focusEffectDisabled()
        .onKeyPress(keys: [.leftArrow, .rightArrow, .upArrow, .downArrow, .return]) { press in
            switch press.key {
            case .leftArrow, .upArrow: move(by: -1)
            case .rightArrow, .downArrow: move(by: 1)
            default:
                guard let action = onReturn ?? onActivateFront, items.indices.contains(focus) else { return .ignored }
                action(items[focus])
            }
            return .handled
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Crate")
        .accessibilityValue(accessibilityValue)
        .accessibilityHint(mode == .sideToSide ? "Records flip side to side" : "Records flip front to back")
        .accessibilityAdjustableAction { direction in
            switch direction {
            case .increment: move(by: 1)
            case .decrement: move(by: -1)
            @unknown default: break
            }
        }
        .accessibilityAction(named: Text(focusedActivateLabel)) {
            if let onActivateFront, items.indices.contains(focus) { onActivateFront(items[focus]) }
        }
        .accessibilityIdentifier("crate")
    }

    private var focusedActivateLabel: String {
        guard onActivateFront != nil, items.indices.contains(focus) else { return "Pull" }
        return activateLabel(items[focus])
    }

    private var accessibilityValue: String {
        guard items.indices.contains(focus) else { return "Empty" }
        let item = items[focus]
        var parts = [item.title]
        if let subtitle = item.subtitle, !subtitle.isEmpty { parts.append(subtitle) }
        if pulledIDs.contains(item.seed.id) { parts.append("pulled") }
        parts.append("\(focus + 1) of \(items.count)")
        return parts.joined(separator: ", ")
    }

    // MARK: Sleeves

    private func sleeve(at index: Int) -> some View {
        let item = items[index]
        let size = mode.sleeveSize
        let t = CrateLayout.transform(index: index, position: position, mode: mode)
        let anchor: UnitPoint = mode == .frontToBack ? .bottom : .center
        return CrateSleeve(item: item, isPulled: pulledIDs.contains(item.seed.id), size: size)
            .overlay(Color.black.opacity(max(0, 1 - t.brightness)))
            .clipShape(RoundedRectangle(cornerRadius: JukeRadius.sleeve, style: .continuous))
            .shadow(color: .black.opacity(0.28), radius: 18, y: 18)
            .scaleEffect(t.scale, anchor: anchor)
            // SwiftUI's rotation sense matches CSS `rotateY`/`rotateX` (checked with
            // renders: +40° Y recedes the right edge, -40° X brings the top forward),
            // so the prototype's angles are used as they are.
            .rotation3DEffect(.degrees(t.rotationY), axis: (x: 0, y: 1, z: 0), anchor: anchor, perspective: 0.3)
            .rotation3DEffect(.degrees(t.rotationX), axis: (x: 1, y: 0, z: 0), anchor: anchor, perspective: 0.3)
            .offset(x: t.x, y: mode.sleeveTop + t.y)
            .opacity(t.opacity)
            .zIndex(t.zIndex)
            .animation(isDragging ? nil : settle, value: position)
            .animation(settle, value: mode)
            .onTapGesture { tap(index) }
            .allowsHitTesting(t.opacity > 0.05)
    }

    // MARK: Input

    private func tap(_ index: Int) {
        guard !suppressTap else { return }
        hasKeyboardFocus = true
        if index != focus {
            focus = index
        } else if let onActivateFront {
            onActivateFront(items[index])
        }
    }

    private func move(by steps: Int) {
        let next = CrateLayout.clamp(focus + steps, count: items.count)
        guard next != focus else { return }
        focus = next
    }

    private var drag: some Gesture {
        DragGesture(minimumDistance: CrateLayout.dragThreshold)
            .onChanged { value in
                let delta = mode == .frontToBack ? value.translation.height : value.translation.width
                isDragging = true
                suppressTap = true
                dragDelta = delta
            }
            .onEnded { value in
                let delta = mode == .frontToBack ? value.translation.height : value.translation.width
                // SwiftUI reports points per second; the prototype's momentum is per millisecond.
                let velocity = (mode == .frontToBack ? value.velocity.height : value.velocity.width) / 1_000
                let next = CrateLayout.releasedFocus(focus: focus, count: items.count, dragDelta: delta, velocity: velocity, mode: mode)
                isDragging = false
                hasKeyboardFocus = true
                withAnimation(settle) {
                    dragDelta = 0
                    focus = next
                }
                // The click that ends a drag arrives with or just after this; let it pass first.
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { suppressTap = false }
            }
    }

    private func startWheel() {
        let mode = mode
        wheelMonitor.start { event in
            // Trackpad momentum would keep flipping long after the fingers lift;
            // swallow it so the crate stops where the swipe ended.
            if !event.momentumPhase.isEmpty { return true }
            let delta = CrateWheelAccumulator.axisDelta(deltaX: event.scrollingDeltaX, deltaY: event.scrollingDeltaY, mode: mode)
            guard delta != 0 else { return false }
            let step = wheel.add(delta, precise: event.hasPreciseScrollingDeltas)
            if step != 0 { withAnimation(settle) { move(by: step) } }
            return true
        }
    }
}

private struct VisibleSleeve: Identifiable {
    let index: Int
    let id: Radio.ID
}

/// One record: the artwork, or a colour field with the title when there is none,
/// and the check badge once pulled.
struct CrateSleeve: View {
    let item: Radio.CrateItem
    var isPulled = false
    var size: CGFloat
    @Environment(\.jukeTheme) private var theme

    var body: some View {
        ZStack(alignment: .topTrailing) {
            RecordArtwork(url: item.artworkURL, seed: item.spotifyId, title: item.title, subtitle: item.subtitle)
                .frame(width: size, height: size)
            if isPulled {
                Image(systemName: "checkmark")
                    .font(.system(size: 13, weight: .heavy))
                    .foregroundStyle(theme.onAccent.color)
                    .frame(width: 28, height: 28)
                    .background(theme.accent.color, in: Circle())
                    .padding(10)
                    .transition(.scale.combined(with: .opacity))
            }
        }
        .frame(width: size, height: size)
        .animation(JukeMotion.easeOutSoft(0.3), value: isPulled)
    }
}

/// Album art, with a stable two-colour placeholder (and the title) while it
/// loads or when the record has none.
struct RecordArtwork: View {
    let url: URL?
    let seed: String
    var title: String?
    var subtitle: String?

    var body: some View {
        GeometryReader { proxy in
            ZStack {
                placeholder(side: proxy.size.width)
                if let url {
                    AsyncImage(url: url, transaction: Transaction(animation: .easeOut(duration: 0.25))) { phase in
                        if let image = phase.image {
                            image.resizable().aspectRatio(contentMode: .fill).transition(.opacity)
                        }
                    }
                }
            }
            .frame(width: proxy.size.width, height: proxy.size.height)
        }
        .clipped()
    }

    private func placeholder(side: CGFloat) -> some View {
        let colors = Self.placeholderColors(for: seed)
        return ZStack(alignment: .bottomLeading) {
            LinearGradient(colors: [colors.0.color, colors.1.color], startPoint: .topLeading, endPoint: .bottomTrailing)
            if let title, side >= 120 {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(JukeFont.display(side * 0.09, weight: .bold)).lineLimit(2)
                    if let subtitle { Text(subtitle).font(JukeFont.body(side * 0.06)).lineLimit(1).opacity(0.85) }
                }
                .foregroundStyle(.white)
                .shadow(color: .black.opacity(0.3), radius: 2, y: 1)
                .padding(side * 0.07)
            }
        }
    }

    /// Two colours derived from a stable hash of the id, so a record keeps its look.
    nonisolated static func placeholderColors(for seed: String) -> (RGB, RGB) {
        var hash: UInt32 = 5381
        for byte in seed.utf8 { hash = (hash &* 33) ^ UInt32(byte) }
        let hue = Double(hash % 360)
        return (
            RGB(hue: hue, saturation: 0.45, lightness: 0.42),
            RGB(hue: (hue + 40).truncatingRemainder(dividingBy: 360), saturation: 0.5, lightness: 0.28)
        )
    }
}

/// Watches scroll-wheel and trackpad scrolling while the pointer is over the
/// crate. The handler returns whether it used the event.
@MainActor
final class ScrollWheelMonitor {
    private var monitor: Any?

    var isActive: Bool { monitor != nil }

    func start(_ handler: @escaping @MainActor (NSEvent) -> Bool) {
        stop()
        monitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { event in
            let used = MainActor.assumeIsolated { handler(event) }
            return used ? nil : event
        }
    }

    func stop() {
        if let monitor { NSEvent.removeMonitor(monitor) }
        monitor = nil
    }
}
