import SwiftUI

/// What the hero needs from the card: the record's artwork and state, and
/// what the gestures do.
struct RadioHeroModel {
    var artworkURL: URL?
    var albumName: String
    var title: String
    var isPlaying: Bool
    var isPutAway: Bool
    var canSeek: Bool
    var position: (Date) -> TimeInterval
    var duration: TimeInterval
    var togglePlay: () -> Void
    var spin: (Double) -> Void
    var putAway: () -> Void
    var comeBack: () -> Void
}

/// The sleeve and the record, 576 × 196 (reference: `vinylDown`, sleeve flip).
struct RadioHero: View {
    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let model: RadioHeroModel
    @Binding var sleeveOpen: Bool
    /// Live seek preview in seconds while spinning (drives progress and the bubble).
    @Binding var seekDelta: TimeInterval?
    let sleeveOptions: [SleeveOption]

    struct SleeveOption: Identifiable {
        let id: String
        let label: String
        let sub: String
        let run: () -> Void
    }

    private enum Drag {
        case label(moved: Bool)
        case spin(lastAngle: Double, total: Double, velocity: Double, time: Date, moved: Bool)
    }

    @State private var drag: Drag?
    @State private var vinylDx: CGFloat = 0
    @State private var rotationBase: Double = 0
    @State private var spinAnchor = Date()
    @State private var frozenRotation: Double?

    private static let vinylSize: CGFloat = 184

    var body: some View {
        ZStack(alignment: .topLeading) {
            vinyl
                .offset(x: (model.isPutAway ? 120 : 290) + vinylDx, y: 6)
                .animation(isDragging || reduceMotion ? nil : JukeMotion.easeOutSoft(0.9), value: model.isPutAway)
                .zIndex(1)
            sleeve
                .offset(x: 40, y: sleeveOpen ? 22 : 0)
                .scaleEffect(sleeveOpen ? 1.25 : 1, anchor: .center)
                .zIndex(sleeveOpen ? 30 : 2)
            if let seekDelta {
                let target = VinylSeek.previewTarget(position: model.position(.now), duration: model.duration, delta: seekDelta)
                Text(VinylSeek.bubbleText(delta: seekDelta, target: target))
                    .font(JukeFont.mono(13, weight: .semibold))
                    .foregroundStyle(theme.card.color)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(theme.ink.color, in: Capsule())
                    .fixedSize()
                    .offset(x: 400, y: 82)
                    .zIndex(10)
                    .allowsHitTesting(false)
                    .accessibilityLabel("Seeking to \(RadioGesture.clock(target))")
            }
        }
        .frame(width: 576, height: 196, alignment: .topLeading)
        .onChange(of: spinning) { _, _ in rebaseRotation() }
    }

    private var isDragging: Bool { drag != nil }
    private var spinning: Bool { model.isPlaying && !model.isPutAway && !reduceMotion && frozenRotation == nil }

    // MARK: Vinyl

    private var vinyl: some View {
        TimelineView(.animation(paused: !spinning)) { context in
            // Equatable + rasterized: each frame only rotates a layer.
            VinylRecord(artworkURL: model.artworkURL, hole: theme.card.color)
                .equatable()
                .rotationEffect(.degrees(rotation(at: context.date)))
        }
        .frame(width: Self.vinylSize, height: Self.vinylSize)
        .shadow(color: .black.opacity(0.28), radius: 15, y: 12)
        .contentShape(Circle())
        .gesture(vinylGesture)
        .help("Spin the edge to seek. Grab the label to slide it in or out of the sleeve.")
        .accessibilityElement()
        .accessibilityLabel("Record")
        .accessibilityValue(model.isPutAway ? "In the sleeve" : (model.isPlaying ? "Playing" : "Paused"))
        .accessibilityHint("Activate to play or pause. Use actions to put the record away or seek.")
        .accessibilityAddTraits(.isButton)
        .accessibilityAction { model.isPutAway ? model.comeBack() : model.togglePlay() }
        .accessibilityAction(named: Text(model.isPutAway ? "Take the record out" : "Put the record away")) {
            model.isPutAway ? model.comeBack() : model.putAway()
        }
        .accessibilityAction(named: Text("Seek forward 15 seconds")) { model.spin(VinylSeek.degrees(forSeconds: 15)) }
        .accessibilityAction(named: Text("Seek back 15 seconds")) { model.spin(VinylSeek.degrees(forSeconds: -15)) }
    }

    private func rotation(at date: Date) -> Double {
        if let frozenRotation, case .spin(_, let total, _, _, _) = drag { return frozenRotation + total * 180 / .pi }
        if let frozenRotation { return frozenRotation }
        guard spinning else { return rotationBase }
        return rotationBase + date.timeIntervalSince(spinAnchor) * 360 / VinylSeek.idleTurnDuration
    }

    private func rebaseRotation() {
        let current = rotation(at: .now)
        rotationBase = current.truncatingRemainder(dividingBy: 360)
        spinAnchor = .now
    }

    private var vinylGesture: some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .local)
            .onChanged { value in
                let size = CGSize(width: Self.vinylSize, height: Self.vinylSize)
                if drag == nil {
                    if model.isPutAway || VinylSeek.isLabelGrab(value.startLocation, in: size) || !model.canSeek {
                        drag = .label(moved: false)
                    } else {
                        frozenRotation = rotation(at: .now)
                        drag = .spin(lastAngle: VinylSeek.angle(of: value.startLocation, in: size), total: 0, velocity: 0, time: .now, moved: false)
                    }
                }
                switch drag {
                case .label(let moved):
                    let dx = value.translation.width
                    let isMoved = moved || abs(dx) > VinylLabelSlide.moveThreshold
                    drag = .label(moved: isMoved)
                    if isMoved, model.canSeek || model.isPutAway { vinylDx = VinylLabelSlide.clamped(dx, putAway: model.isPutAway) }
                case .spin(let last, let total, let velocity, let time, let moved):
                    let angle = VinylSeek.angle(of: value.location, in: size)
                    let delta = VinylSeek.wrappedDelta(from: last, to: angle)
                    let now = Date()
                    let v = RadioGesture.smoothedVelocity(previous: velocity, delta: delta * 180 / .pi,
                                                         dtMilliseconds: now.timeIntervalSince(time) * 1000, weight: 0.7)
                    let newTotal = total + delta
                    let degrees = newTotal * 180 / .pi
                    let isMoved = moved || abs(degrees) > VinylSeek.spinThresholdDegrees
                    drag = .spin(lastAngle: angle, total: newTotal, velocity: v, time: now, moved: isMoved)
                    if isMoved { seekDelta = VinylSeek.seconds(forDegrees: degrees) }
                case nil:
                    break
                }
            }
            .onEnded { value in
                let ended = drag
                drag = nil
                switch ended {
                case .label(let moved):
                    let dx = value.translation.width
                    withAnimation(reduceMotion ? nil : JukeMotion.easeOutSoft(0.9)) { vinylDx = 0 }
                    if !moved {
                        model.isPutAway ? model.comeBack() : model.togglePlay()
                        return
                    }
                    switch VinylLabelSlide.outcome(dx: dx, putAway: model.isPutAway) {
                    case .putAway:
                        sleeveOpen = false
                        model.putAway()
                    case .resume:
                        model.comeBack()
                    case .none:
                        break
                    }
                case .spin(_, let total, let velocity, let time, let moved):
                    let frozen = frozenRotation ?? rotationBase
                    frozenRotation = nil
                    seekDelta = nil
                    guard moved else {
                        rotationBase = frozen
                        spinAnchor = .now
                        model.togglePlay()
                        return
                    }
                    let degrees = VinylSeek.releaseDegrees(dragDegrees: total * 180 / .pi, velocity: velocity,
                                                           sinceLastMove: Date().timeIntervalSince(time))
                    rotationBase = (frozen + degrees).truncatingRemainder(dividingBy: 360)
                    spinAnchor = .now
                    model.spin(degrees)
                case nil:
                    break
                }
            }
    }

    // MARK: Sleeve

    private var sleeve: some View {
        SleeveFlip(angle: sleeveOpen ? 180 : 0) {
            Button { toggleSleeve() } label: {
                RadioArtwork(url: model.artworkURL, cornerRadius: 10)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Sleeve for \(model.title): more options")
            .accessibilityIdentifier("radio.sleeve")
        } back: {
            sleeveBack
        }
        .frame(width: 196, height: 196)
        .shadow(color: .black.opacity(0.22), radius: 17, y: 14)
        .animation(reduceMotion ? nil : JukeMotion.easeOutSoft(0.7), value: sleeveOpen)
    }

    private func toggleSleeve() {
        sleeveOpen.toggle()
    }

    private var sleeveBack: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(model.albumName.uppercased())
                    .font(JukeFont.body(10, weight: .bold))
                    .tracking(1.2)
                    .foregroundStyle(theme.sub.color)
                    .lineLimit(1)
                Spacer(minLength: 4)
                Button { toggleSleeve() } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(theme.sub.color)
                        .frame(width: 28, height: 28)
                        .contentShape(Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Close sleeve")
            }
            .padding(.horizontal, 4)
            .padding(.bottom, 4)
            ForEach(sleeveOptions) { option in
                Button {
                    sleeveOpen = false
                    option.run()
                } label: {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(option.label).font(JukeFont.body(13, weight: .bold)).foregroundStyle(theme.ink.color)
                        Text(option.sub).font(JukeFont.body(10)).foregroundStyle(theme.sub.color).lineLimit(1)
                    }
                    .frame(maxWidth: .infinity, minHeight: 34, alignment: .leading)
                    .padding(.horizontal, 8)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("radio.sleeve.\(option.id)")
            }
            Spacer(minLength: 0)
        }
        .padding(EdgeInsets(top: 10, leading: 8, bottom: 8, trailing: 8))
        .frame(width: 196, height: 196, alignment: .topLeading)
        .background(theme.sleeveBack.color, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

/// A 3D card flip that shows the back face past 90°.
private struct SleeveFlip<Front: View, Back: View>: @MainActor Animatable, View {
    var angle: Double
    @ViewBuilder var front: Front
    @ViewBuilder var back: Back

    var animatableData: Double {
        get { angle }
        set { angle = newValue }
    }

    var body: some View {
        ZStack {
            front
                .opacity(angle < 90 ? 1 : 0)
                .accessibilityHidden(angle >= 90)
            back
                .rotation3DEffect(.degrees(180), axis: (x: 0, y: 1, z: 0))
                .opacity(angle >= 90 ? 1 : 0)
                .accessibilityHidden(angle < 90)
                .allowsHitTesting(angle >= 90)
        }
        .rotation3DEffect(.degrees(angle), axis: (x: 0, y: 1, z: 0), perspective: 0.5)
    }
}

/// The 184 pt record: grooves, the artwork label and the spindle hole.
struct VinylRecord: View, Equatable {
    let artworkURL: URL?
    let hole: Color

    var body: some View {
        ZStack {
            Canvas { canvas, area in
                let rect = CGRect(origin: .zero, size: area)
                canvas.fill(Path(ellipseIn: rect), with: .color(Color(red: 0.08, green: 0.08, blue: 0.08)))
                var radius = area.width / 2 - 2
                while radius > area.width * 0.2 {
                    let ring = rect.insetBy(dx: area.width / 2 - radius, dy: area.height / 2 - radius)
                    canvas.stroke(Path(ellipseIn: ring), with: .color(Color(red: 0.14, green: 0.14, blue: 0.14)), lineWidth: 1)
                    radius -= 5
                }
            }
            RadioArtwork(url: artworkURL, cornerRadius: 35)
                .frame(width: 70, height: 70)
                .clipShape(Circle())
            Circle().fill(hole).frame(width: 8, height: 8)
        }
        .accessibilityHidden(true)
    }
}
