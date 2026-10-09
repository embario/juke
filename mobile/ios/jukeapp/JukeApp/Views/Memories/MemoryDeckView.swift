import SwiftUI

/// The Memories landing: a shuffled deck of print-style cards. Photos and song artwork lead;
/// swipe the top card away (or use the arrows) to see the next one, tap to open it.
struct MemoryDeckView: View {
    @Environment(VibeAppModel.self) private var model
    let memories: [MusicMemory]
    let question: String
    /// The visible height of the page; the deck is at least this tall (so it centres) and taller when text is large.
    let minHeight: CGFloat
    let open: (MusicMemory) -> Void
    let delete: (MusicMemory) -> Void

    @State private var deck = MemoryDeck()
    @State private var drag: CGSize = .zero
    @State private var seed: UInt64 = MemoryDeckView.initialSeed()
    @State private var pageWidth: CGFloat = 390
    @Environment(\.dynamicTypeSize) private var typeSize
    /// The island and tab bar grow with text size, so the room kept for them does too.
    @ScaledMetric(relativeTo: .body) private var islandInset = MemoryDeckStyle.islandInset

    private static func initialSeed() -> UInt64 {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--uitesting") { return 7 }
        #endif
        return UInt64.random(in: .min ... .max)
    }

    private func memory(_ id: UUID) -> MusicMemory? { memories.first { $0.id == id } }

    var body: some View {
        let width = min(pageWidth - 56, 340)
        VStack(spacing: 18) {
            Spacer(minLength: 0)
            ZStack(alignment: .top) {
                ForEach(Array(deck.visible(limit: typeSize.isAccessibilitySize ? 1 : 3).enumerated().reversed()), id: \.element) { index, id in
                    if let memory = memory(id) {
                        card(memory, index: index, width: width)
                    }
                }
            }
            .frame(width: width)
            Controls
            if !question.isEmpty {
                Text(question).font(.footnote).italic().multilineTextAlignment(.center)
                    .foregroundStyle(.secondary).padding(.horizontal, 28)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 12)
        .padding(.bottom, islandInset)  // clear of the player island and tab bar that float over the page
        // At least a screen tall so a small deck stays centred; taller content (large text) scrolls with the page.
        .frame(maxWidth: .infinity, minHeight: minHeight)
        .background(GeometryReader { proxy in Color.clear.preference(key: DeckWidthKey.self, value: proxy.size.width) })
        .onPreferenceChange(DeckWidthKey.self) { if $0 > 0 { pageWidth = $0 } }
        .onAppear { deck.sync(with: memories, seed: seed) }
        .onChange(of: memories) { _, value in deck.sync(with: value, seed: seed &+ UInt64(value.count)) }
    }

    private func rotation(isTop: Bool, index: Int, tilt: Double) -> Double {
        if isTop { return tilt + Double(drag.width) / 22 }
        return tilt * (index == 1 ? -1.4 : 1.8)
    }

    @ViewBuilder
    private func card(_ memory: MusicMemory, index: Int, width: CGFloat) -> some View {
        let isTop = index == 0
        let tilt = MemoryDeckStyle.tilt(for: memory.id)
        MemoryCard(memory: memory, width: width, playing: model.memoryPlayer.current?.memoryID == memory.id)
            .rotationEffect(.degrees(rotation(isTop: isTop, index: index, tilt: tilt)))
            .offset(x: isTop ? drag.width : 0, y: isTop ? drag.height / 3 : CGFloat(index) * 12)
            .scaleEffect(1 - CGFloat(index) * 0.05)
            .opacity(isTop ? 1 : 1 - Double(index) * 0.12)
            .zIndex(Double(10 - index))
            .allowsHitTesting(isTop)
            .onTapGesture { open(memory) }
            .gesture(swipe)  // behind-cards do not hit-test, so only the top card ever receives it
            .contextMenu {
                Button("Open", systemImage: "arrow.up.right.square") { open(memory) }
                Button("Delete", systemImage: "trash", role: .destructive) { delete(memory) }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(MemoryDeckStyle.accessibilityLabel(memory))
            .accessibilityValue(model.memoryPlayer.current?.memoryID == memory.id ? "Playing" : "")
            .accessibilityHint("Opens the memory")
            .accessibilityAddTraits(.isButton)
            .accessibilityIdentifier(isTop ? "memory.card" : "memory.card.behind")
            .accessibilityHidden(!isTop)
            .animation(.spring(response: 0.38, dampingFraction: 0.82), value: deck)
    }

    /// A pan that only starts for a sideways drag, so vertical drags keep scrolling the page
    /// (a SwiftUI DragGesture on the card would take every drag and stop the scroll).
    private var swipe: SidewaysPanGesture {
        SidewaysPanGesture(
            onChange: { drag = $0 },
            onEnd: { translation, velocityX in
                guard MemoryDeckStyle.shouldAdvance(translation: translation.width, predicted: translation.width + velocityX * 0.25) else {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) { drag = .zero }
                    return
                }
                withAnimation(.easeIn(duration: 0.16)) { drag = CGSize(width: translation.width > 0 ? 520 : -520, height: translation.height) }
                Task { @MainActor in
                    try? await Task.sleep(for: .milliseconds(160))
                    drag = .zero
                    if translation.width > 0 { deck.retreat() } else { deck.advance() }
                }
            },
            onCancel: { withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) { drag = .zero } }
        )
    }

    private var Controls: some View {
        let position = Text(deck.count > 0 ? "\(deck.position) of \(deck.count)" : "")
            .font(.subheadline.monospacedDigit()).foregroundStyle(.secondary)
            .frame(minWidth: 72).accessibilityIdentifier("memory.position")
        return VStack(spacing: 10) {
            // At accessibility sizes the count gets its own line so the buttons never crowd it.
            if typeSize.isAccessibilitySize { position }
            HStack(spacing: 14) {
                roundButton("chevron.left", "Previous memory", id: "memory.deck.previous") { withAnimation { deck.retreat() } }
                if !typeSize.isAccessibilitySize { position }
                roundButton("chevron.right", "Next memory", id: "memory.deck.next") { withAnimation { deck.advance() } }
                roundButton("shuffle", "Shuffle memories", id: "memory.deck.shuffle") {
                    seed = seed &+ 0x9E37
                    withAnimation(.spring(response: 0.5, dampingFraction: 0.75)) { deck.reshuffle(memories, seed: seed) }
                }
                .padding(.leading, typeSize.isAccessibilitySize ? 0 : 8)
                if let top = deck.top.flatMap(memory) {
                    Menu {
                        Button("Open", systemImage: "arrow.up.right.square") { open(top) }
                        Button("Delete", systemImage: "trash", role: .destructive) { delete(top) }.accessibilityIdentifier("memory.delete")
                    } label: {
                        Image(systemName: "ellipsis").font(.system(size: 17, weight: .semibold)).frame(width: 44, height: 44).background(.thinMaterial, in: Circle())
                    }
                    .accessibilityLabel("More for this memory").accessibilityIdentifier("memory.menu")
                }
            }
        }
        .disabled(deck.isEmpty)
    }

    private func roundButton(_ symbol: String, _ label: String, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol).font(.system(size: 17, weight: .semibold)).frame(width: 44, height: 44)
                .background(.thinMaterial, in: Circle())
        }
        .buttonStyle(.plain)
        .disabled(deck.count < 2)
        .accessibilityLabel(label).accessibilityIdentifier(id)
    }
}

private struct DeckWidthKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}

/// One print-style card: the memory's photo (or a video frame, or the song's artwork) with a caption underneath.
private struct MemoryCard: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.colorScheme) private var scheme
    let memory: MusicMemory
    let width: CGFloat
    let playing: Bool
    @Environment(\.dynamicTypeSize) private var typeSize

    /// Normal sizes keep the print tidy; larger text may wrap instead of being cut off.
    private var titleLines: Int? { typeSize.isAccessibilitySize ? nil : 2 }
    private var captionLines: Int? { typeSize.isAccessibilitySize ? nil : 1 }

    var body: some View {
        let inner = width - 24
        VStack(alignment: .leading, spacing: 10) {
            ZStack(alignment: .topTrailing) {
                if case .placeholder = MemoryThumbnailChoice.choose(for: memory) {
                    MemoryDeckStyle.gradient(for: memory.id)
                        .overlay { Image(systemName: "music.note").font(.system(size: inner * 0.28)).foregroundStyle(.white.opacity(0.85)) }
                        .frame(width: inner, height: inner)
                } else {
                    MemoryThumbnail(memory: memory, side: inner, cornerRadius: 3)
                }
                if playing {
                    Image(systemName: "waveform").padding(8).background(.ultraThinMaterial, in: Circle()).padding(8)
                        .foregroundStyle(model.atmosphere.primary)
                        .accessibilityLabel("Playing").accessibilityIdentifier("memory.playing")
                }
                if let art = memory.songs.compactMap(\.artworkURL).first, MemoryThumbnailChoice.choose(for: memory) != .artwork(art) {
                    AsyncImage(url: art) { $0.resizable().scaledToFill() } placeholder: { Color.secondary.opacity(0.2) }
                        .frame(width: inner * 0.28, height: inner * 0.28).clipShape(RoundedRectangle(cornerRadius: 6))
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(.white, lineWidth: 2))
                        .shadow(radius: 4).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading).padding(10)
                        .allowsHitTesting(false)
                }
            }
            .frame(width: inner, height: inner)
            VStack(alignment: .leading, spacing: 3) {
                Text(memory.displayTitle).font(.system(.title3, design: .rounded, weight: .bold)).lineLimit(titleLines)
                Text(MemoryDeckStyle.subtitle(memory)).font(.footnote).foregroundStyle(MemoryDeckStyle.caption(scheme)).lineLimit(captionLines)
                if let song = memory.songs.first {
                    Label("\(song.title) — \(song.artist)", systemImage: "music.note").font(.footnote.weight(.medium)).lineLimit(captionLines)
                }
            }
            .foregroundStyle(MemoryDeckStyle.ink(scheme))
            .padding(.horizontal, 4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .frame(width: width, alignment: .top)
        .background(MemoryDeckStyle.paper(scheme), in: RoundedRectangle(cornerRadius: 6))
        .overlay(RoundedRectangle(cornerRadius: 6).stroke(.black.opacity(scheme == .dark ? 0.5 : 0.08), lineWidth: 1))
        .shadow(color: .black.opacity(0.28), radius: 14, y: 8)
    }
}

/// Look-and-feel decisions, kept apart from the view so they can be tested.
enum MemoryDeckStyle {
    /// Space reserved under the deck for the floating player island and tab bar.
    static let islandInset: CGFloat = 150

    static func tilt(for id: UUID) -> Double {
        let value = id.uuid.0
        return (Double(value) / 255 * 6) - 3  // -3...3 degrees, stable per memory
    }

    /// A drag counts as a card swipe only when it is mostly horizontal.
    static func isSideways(_ translation: CGSize) -> Bool { abs(translation.width) > abs(translation.height) * 1.2 }

    static func shouldAdvance(translation: CGFloat, predicted: CGFloat) -> Bool {
        abs(translation) > 100 || abs(predicted) > 260
    }

    static func subtitle(_ memory: MusicMemory) -> String {
        let date = memory.occurredAt.formatted(date: .abbreviated, time: .omitted)
        return memory.place.isEmpty ? date : "\(date) · \(memory.place)"
    }

    static func accessibilityLabel(_ memory: MusicMemory) -> String {
        var parts = [memory.displayTitle, subtitle(memory)]
        if let song = memory.songs.first { parts.append("\(song.title) by \(song.artist)") }
        return parts.joined(separator: ", ")
    }

    /// A calm gradient for memories with neither a photo nor artwork.
    static func gradient(for id: UUID) -> LinearGradient {
        let bytes = id.uuid
        let hue = Double(bytes.1) / 255
        return LinearGradient(colors: [Color(hue: hue, saturation: 0.45, brightness: 0.85), Color(hue: (hue + 0.12).truncatingRemainder(dividingBy: 1), saturation: 0.6, brightness: 0.6)],
                              startPoint: .topLeading, endPoint: .bottomTrailing)
    }

    static func paper(_ scheme: ColorScheme) -> Color { scheme == .dark ? Color(white: 0.17) : Color(red: 0.99, green: 0.98, blue: 0.96) }
    static func ink(_ scheme: ColorScheme) -> Color { scheme == .dark ? .white : Color(white: 0.12) }
    static func caption(_ scheme: ColorScheme) -> Color { scheme == .dark ? Color(white: 0.7) : Color(white: 0.4) }
}

/// Recognises a drag only when it starts out mostly sideways; a mostly vertical one fails at once
/// so the enclosing scroll view gets it.
struct SidewaysPanGesture: UIGestureRecognizerRepresentable {
    let onChange: (CGSize) -> Void
    let onEnd: (CGSize, CGFloat) -> Void
    let onCancel: () -> Void

    func makeUIGestureRecognizer(context: Context) -> SidewaysPanRecognizer { SidewaysPanRecognizer() }

    func handleUIGestureRecognizerAction(_ recognizer: SidewaysPanRecognizer, context: Context) {
        let translation = recognizer.translation(in: recognizer.view)
        let size = CGSize(width: translation.x, height: translation.y)
        switch recognizer.state {
        case .began, .changed: onChange(size)
        case .ended: onEnd(size, recognizer.velocity(in: recognizer.view).x)
        case .cancelled, .failed: onCancel()
        default: break
        }
    }
}

final class SidewaysPanRecognizer: UIPanGestureRecognizer {
    private var origin: CGPoint?
    private var decided = false

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent) {
        origin = touches.first?.location(in: nil)
        decided = false
        super.touchesBegan(touches, with: event)
    }

    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent) {
        if !decided, let origin, let point = touches.first?.location(in: nil) {
            let delta = CGSize(width: point.x - origin.x, height: point.y - origin.y)
            if abs(delta.width) + abs(delta.height) > 8 {
                decided = true
                if !MemoryDeckStyle.isSideways(delta) { state = .failed; return }
            }
        }
        super.touchesMoved(touches, with: event)
    }

    override func reset() {
        super.reset()
        origin = nil
        decided = false
    }
}
