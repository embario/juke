import SwiftUI

enum MemoryIllustrationKind: Equatable { case photo, song, story, review, complete }

extension EnvironmentValues {
    /// Accent derived from the memory's own artwork or lead photo; orange until one exists.
    @Entry var journeyAccent: Color = .orange
}

struct MemoryJourneyIllustration: View {
    let kind: MemoryIllustrationKind
    var image: NSImage?
    var artwork: NSImage?
    var spinning = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.journeyAccent) private var accent
    @State private var floating = false

    var body: some View {
        GeometryReader { geometry in
            let side = min(geometry.size.width, geometry.size.height, 290.0)
            ZStack {
                Circle().fill(accent.opacity(0.1)).frame(width: side, height: side)
                Circle().stroke(accent.opacity(0.14), style: StrokeStyle(lineWidth: 1, dash: [3, 8])).frame(width: side * 1.1, height: side * 1.1)
                if kind == .song {
                    SpinningRecord(artwork: artwork, spinning: spinning).frame(width: side * 0.78, height: side * 0.78)
                        .rotationEffect(.degrees(spinning || reduceMotion ? 0 : (floating ? 6 : -6)))
                } else {
                    RoundedRectangle(cornerRadius: 12).fill(accent.opacity(0.24)).frame(width: side * 0.7, height: side * 0.84).rotationEffect(.degrees(-13)).offset(x: -12, y: 5)
                    VStack(spacing: 0) {
                        Group {
                            if let image { Image(nsImage: image).resizable().scaledToFill() }
                            else { landscape }
                        }.frame(width: side * 0.66, height: side * 0.60).clipped().clipShape(RoundedRectangle(cornerRadius: 5))
                        HStack { Rectangle().fill(.black.opacity(0.1)).frame(width: side * 0.2, height: 3); Spacer(); Image(systemName: kind == .complete ? "heart.fill" : "sparkle").foregroundStyle(accent) }.padding(.top, 13).padding(.horizontal, 8)
                    }.padding(10).padding(.bottom, 8).background(.white, in: RoundedRectangle(cornerRadius: 12))
                        .shadow(color: .black.opacity(0.08), radius: 15, y: 8)
                        .rotationEffect(.degrees(floating && !reduceMotion ? 5 : 2)).offset(y: floating && !reduceMotion ? -7 : 1)
                    if kind == .review || kind == .complete || (kind == .story && artwork != nil) {
                        SpinningRecord(artwork: artwork, spinning: spinning).frame(width: side * 0.38, height: side * 0.38).offset(x: side * 0.3, y: side * 0.27)
                    }
                    if kind == .story { Image(systemName: "quote.opening").font(.system(size: side * 0.23, weight: .heavy, design: .serif)).foregroundStyle(accent).offset(x: -side * 0.32, y: -side * 0.3) }
                }
                ForEach(0..<5) { index in
                    Image(systemName: kind == .complete ? "sparkle" : "music.note")
                        .font(.system(size: CGFloat(10 + index * 2))).foregroundStyle(index.isMultiple(of: 2) ? accent.opacity(0.7) : .purple.opacity(0.4))
                        .offset(x: cos(Double(index) * 1.3) * side * 0.46, y: sin(Double(index) * 1.3) * side * 0.45 + (floating && !reduceMotion ? -8 : 0))
                }
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
        }.accessibilityHidden(true)
            .onAppear { guard !reduceMotion else { return }; withAnimation(.easeInOut(duration: 3).repeatForever(autoreverses: true)) { floating = true } }
    }
    private var landscape: some View {
        GeometryReader { g in
            ZStack {
                LinearGradient(colors: [Color(red: 0.95, green: 0.68, blue: 0.48), Color(red: 0.99, green: 0.83, blue: 0.64)], startPoint: .top, endPoint: .bottom)
                Circle().fill(Color(red: 1, green: 0.92, blue: 0.72)).frame(width: 48, height: 48).offset(x: 35, y: -25)
                Path { p in p.move(to: CGPoint(x: 0, y: g.size.height * 0.65)); p.addQuadCurve(to: CGPoint(x: g.size.width, y: g.size.height * 0.6), control: CGPoint(x: g.size.width * 0.4, y: g.size.height * 0.1)); p.addLine(to: CGPoint(x: g.size.width, y: g.size.height)); p.addLine(to: CGPoint(x: 0, y: g.size.height)) }.fill(Color(red: 0.64, green: 0.55, blue: 0.72))
                Path { p in p.move(to: CGPoint(x: 0, y: g.size.height * 0.8)); p.addQuadCurve(to: CGPoint(x: g.size.width, y: g.size.height * 0.72), control: CGPoint(x: g.size.width * 0.7, y: g.size.height * 0.4)); p.addLine(to: CGPoint(x: g.size.width, y: g.size.height)); p.addLine(to: CGPoint(x: 0, y: g.size.height)) }.fill(Color(red: 0.35, green: 0.42, blue: 0.48))
            }
        }
    }
}

/// A vinyl record whose label is the song's artwork. It turns at 33⅓ rpm only while that song plays.
struct SpinningRecord: View {
    var artwork: NSImage?
    var spinning: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.journeyAccent) private var accent

    var body: some View {
        TimelineView(.animation(paused: !spinning || reduceMotion)) { context in
            let degrees = spinning && !reduceMotion ? context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.8) / 1.8 * 360 : 0
            ZStack {
                Circle().fill(Color(red: 0.17, green: 0.16, blue: 0.23))
                ForEach(0..<5) { index in Circle().stroke(.white.opacity(0.08), lineWidth: 1).padding(CGFloat(10 + index * 8)) }
                Group {
                    if let artwork { Image(nsImage: artwork).resizable().scaledToFill() } else { accent }
                }.clipShape(Circle()).scaleEffect(0.38)
                Circle().fill(.white.opacity(0.85)).scaleEffect(0.04)
            }.rotationEffect(.degrees(degrees))
        }
    }
}

/// The composer's primary pill: the Juke accent, like every other primary action.
struct JourneyButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    @Environment(\.jukeTheme) private var theme
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(JukeFont.body(14, weight: .bold))
            .padding(.horizontal, 22).frame(minHeight: JukeMetrics.minimumHitTarget)
            .foregroundStyle(enabled ? theme.onAccent.color : theme.sub.color)
            .background(enabled ? theme.accent.color : theme.well.color, in: Capsule())
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .contentShape(Capsule())
    }
}

/// Loads remote artwork once per URL for the journey's record labels and accent color.
@MainActor @Observable
final class JourneyArtworkCache {
    private(set) var images: [URL: NSImage] = [:]
    private(set) var colors: [URL: Color] = [:]
    @ObservationIgnored private var inFlight = Set<URL>()

    func load(_ url: URL?) {
        guard let url, images[url] == nil, inFlight.insert(url).inserted else { return }
        Task {
            defer { inFlight.remove(url) }
            guard let (data, _) = try? await URLSession.shared.data(from: url), data.count < 12_000_000, let image = NSImage(data: data) else { return }
            images[url] = image
            if let color = ArtworkPalette.averageColor(image) { colors[url] = .journeyAccent(from: color) }
        }
    }
}

/// A two-handle range control for choosing the part of a song worth keeping.
struct SnippetRangeSlider: View {
    @Binding var start: Double
    @Binding var end: Double
    let duration: Double
    var playhead: Double?
    @Environment(\.journeyAccent) private var accent
    private let minimumLength = 5.0

    var body: some View {
        GeometryReader { geometry in
            let width = max(1, geometry.size.width - 18)
            let x = { (value: Double) in CGFloat(min(max(value / max(duration, 1), 0), 1)) * width + 9 }
            ZStack(alignment: .leading) {
                Capsule().fill(Color.primary.opacity(0.08)).frame(height: 8).padding(.horizontal, 9)
                Capsule().fill(accent.opacity(0.55)).frame(width: max(8, x(end) - x(start)), height: 8).offset(x: x(start))
                if let playhead, playhead >= 0, playhead <= duration {
                    Rectangle().fill(Color.primary.opacity(0.6)).frame(width: 2, height: 18).offset(x: x(playhead) - 1)
                }
                handle.offset(x: x(start) - 9).gesture(DragGesture(coordinateSpace: .named("snippet")).onChanged { value in
                    start = min(max(0, Double((value.location.x - 9) / width) * duration), end - minimumLength).rounded()
                }).accessibilityLabel("Snippet start").accessibilityValue(MemorySong.timestamp(start))
                    .accessibilityAdjustableAction { direction in start = direction == .increment ? min(start + 1, end - minimumLength) : max(0, start - 1) }
                handle.offset(x: x(end) - 9).gesture(DragGesture(coordinateSpace: .named("snippet")).onChanged { value in
                    end = max(min(duration, Double((value.location.x - 9) / width) * duration), start + minimumLength).rounded()
                }).accessibilityLabel("Snippet end").accessibilityValue(MemorySong.timestamp(end))
                    .accessibilityAdjustableAction { direction in end = direction == .increment ? min(duration, end + 1) : max(start + minimumLength, end - 1) }
            }.frame(maxHeight: .infinity).coordinateSpace(.named("snippet"))
        }.frame(height: 26)
    }
    private var handle: some View {
        Circle().fill(.white).frame(width: 18, height: 18).shadow(color: .black.opacity(0.25), radius: 2, y: 1)
            .overlay(Circle().stroke(accent, lineWidth: 2)).contentShape(Circle().inset(by: -6))
    }
}

extension Color {
    /// Average artwork colors are often muddy; lift them into a readable, still-recognizable accent.
    static func journeyAccent(from color: NSColor) -> Color {
        let rgb = color.usingColorSpace(.sRGB) ?? color
        var hue: CGFloat = 0, saturation: CGFloat = 0, brightness: CGFloat = 0, alpha: CGFloat = 0
        rgb.getHue(&hue, saturation: &saturation, brightness: &brightness, alpha: &alpha)
        guard saturation > 0.08 else { return .orange }
        return Color(hue: hue, saturation: min(0.85, max(saturation, 0.45)), brightness: min(0.9, max(brightness, 0.62)))
    }
}
