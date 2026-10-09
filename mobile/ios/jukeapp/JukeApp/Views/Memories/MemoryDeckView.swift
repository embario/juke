import SwiftUI

/// The Memories landing: a shuffled deck of print-style cards. Photos and song artwork lead;
/// swipe the top card away (or use the arrows) to see the next one, tap to open it.
struct MemoryDeckView: View {
    @Environment(VibeAppModel.self) private var model
    let memories: [MusicMemory]
    let question: String
    let open: (MusicMemory) -> Void
    let delete: (MusicMemory) -> Void

    @State private var deck = MemoryDeck()
    @State private var drag: CGSize = .zero
    @State private var seed: UInt64 = MemoryDeckView.initialSeed()

    private static func initialSeed() -> UInt64 {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--uitesting") { return 7 }
        #endif
        return UInt64.random(in: .min ... .max)
    }

    private func memory(_ id: UUID) -> MusicMemory? { memories.first { $0.id == id } }

    var body: some View {
        GeometryReader { geometry in
            let width = min(geometry.size.width - 56, 340)
            VStack(spacing: 18) {
                Spacer(minLength: 0)
                ZStack {
                    ForEach(Array(deck.visible().enumerated().reversed()), id: \.element) { index, id in
                        if let memory = memory(id) {
                            card(memory, index: index, width: width)
                        }
                    }
                }
                .frame(width: width, height: width * 1.22)
                Controls
                if !question.isEmpty {
                    Text(question).font(.footnote).italic().lineLimit(2).multilineTextAlignment(.center)
                        .foregroundStyle(.secondary).padding(.horizontal, 28)
                }
                Spacer(minLength: 0)
            }
            .padding(.bottom, 104)  // clear of the player island and tab bar that float over the page
            .frame(maxWidth: .infinity)
        }
        .onAppear { deck.sync(with: memories, seed: seed) }
        .onChange(of: memories) { _, value in deck.sync(with: value, seed: seed &+ UInt64(value.count)) }
    }

    @ViewBuilder
    private func card(_ memory: MusicMemory, index: Int, width: CGFloat) -> some View {
        let isTop = index == 0
        let tilt = MemoryDeckStyle.tilt(for: memory.id)
        MemoryCard(memory: memory, width: width, playing: model.memoryPlayer.current?.memoryID == memory.id)
            .rotationEffect(.degrees(isTop ? tilt + Double(drag.width) / 22 : tilt * (index == 1 ? -1.4 : 1.8)))
            .offset(x: isTop ? drag.width : 0, y: isTop ? drag.height / 3 : CGFloat(index) * 12)
            .scaleEffect(1 - CGFloat(index) * 0.05)
            .opacity(isTop ? 1 : 1 - Double(index) * 0.12)
            .zIndex(Double(10 - index))
            .allowsHitTesting(isTop)
            .onTapGesture { open(memory) }
            .gesture(isTop ? swipe : nil)
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

    private var swipe: some Gesture {
        DragGesture(minimumDistance: 12)
            .onChanged { drag = $0.translation }
            .onEnded { value in
                if MemoryDeckStyle.shouldAdvance(translation: value.translation.width, predicted: value.predictedEndTranslation.width) {
                    withAnimation(.easeIn(duration: 0.16)) { drag = CGSize(width: value.translation.width > 0 ? 520 : -520, height: value.translation.height) }
                    Task { @MainActor in
                        try? await Task.sleep(for: .milliseconds(160))
                        drag = .zero
                        if value.translation.width > 0 { deck.retreat() } else { deck.advance() }
                    }
                } else {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) { drag = .zero }
                }
            }
    }

    private var Controls: some View {
        HStack(spacing: 14) {
            roundButton("chevron.left", "Previous memory", id: "memory.deck.previous") { withAnimation { deck.retreat() } }
            Text(deck.count > 0 ? "\(deck.position) of \(deck.count)" : "")
                .font(.subheadline.monospacedDigit()).foregroundStyle(.secondary)
                .frame(minWidth: 72).accessibilityIdentifier("memory.position")
            roundButton("chevron.right", "Next memory", id: "memory.deck.next") { withAnimation { deck.advance() } }
            roundButton("shuffle", "Shuffle memories", id: "memory.deck.shuffle") {
                seed = seed &+ 0x9E37
                withAnimation(.spring(response: 0.5, dampingFraction: 0.75)) { deck.reshuffle(memories, seed: seed) }
            }
            .padding(.leading, 8)
            if let top = deck.top.flatMap(memory) {
                Menu {
                    Button("Open", systemImage: "arrow.up.right.square") { open(top) }
                    Button("Delete", systemImage: "trash", role: .destructive) { delete(top) }.accessibilityIdentifier("memory.delete")
                } label: {
                    Image(systemName: "ellipsis").frame(width: 44, height: 44).background(.thinMaterial, in: Circle())
                }
                .accessibilityLabel("More for this memory").accessibilityIdentifier("memory.menu")
            }
        }
        .disabled(deck.isEmpty)
    }

    private func roundButton(_ symbol: String, _ label: String, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol).font(.body.weight(.semibold)).frame(width: 44, height: 44)
                .background(.thinMaterial, in: Circle())
        }
        .buttonStyle(.plain)
        .disabled(deck.count < 2)
        .accessibilityLabel(label).accessibilityIdentifier(id)
    }
}

/// One print-style card: the memory's photo (or a video frame, or the song's artwork) with a caption underneath.
private struct MemoryCard: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.colorScheme) private var scheme
    let memory: MusicMemory
    let width: CGFloat
    let playing: Bool

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
                Text(memory.displayTitle).font(.system(.title3, design: .rounded, weight: .bold)).lineLimit(1)
                Text(MemoryDeckStyle.subtitle(memory)).font(.footnote).foregroundStyle(MemoryDeckStyle.caption(scheme)).lineLimit(1)
                if let song = memory.songs.first {
                    Label("\(song.title) — \(song.artist)", systemImage: "music.note").font(.footnote.weight(.medium)).lineLimit(1)
                }
            }
            .foregroundStyle(MemoryDeckStyle.ink(scheme))
            .padding(.horizontal, 4)
            Spacer(minLength: 0)
        }
        .padding(12)
        .frame(width: width, height: width * 1.22, alignment: .top)
        .background(MemoryDeckStyle.paper(scheme), in: RoundedRectangle(cornerRadius: 6))
        .overlay(RoundedRectangle(cornerRadius: 6).stroke(.black.opacity(scheme == .dark ? 0.5 : 0.08), lineWidth: 1))
        .shadow(color: .black.opacity(0.28), radius: 14, y: 8)
    }
}

/// Look-and-feel decisions, kept apart from the view so they can be tested.
enum MemoryDeckStyle {
    static func tilt(for id: UUID) -> Double {
        let value = id.uuid.0
        return (Double(value) / 255 * 6) - 3  // -3...3 degrees, stable per memory
    }

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
