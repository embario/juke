import SwiftUI

/// The record. Drag the outer ring to turn it: one full turn seeks 14 s (past the
/// end moves on). Drag the centre label sideways and the whole record follows your
/// finger into (left) or out of (right) the sleeve; let go past the halfway point
/// (or fling) and it settles there, which puts radio away or brings it back. Let go
/// before that, or drag back, and it springs back, so the move can be cancelled.
struct VinylDisc: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let track: Radio.Track?
    let size: CGFloat
    /// Where the record's left edge rests when it is out of the sleeve.
    let outOffset: CGFloat

    private enum Grab { case ring, label }
    @State private var grab: Grab?
    @State private var lastAngle = 0.0
    @State private var spinDegrees = 0.0
    /// Finger-driven offset on top of the resting position (label drags only).
    @State private var slide: CGFloat = 0
    @State private var frame: CGRect = .zero
    /// The idle angle the record rests at, and when it last started turning.
    @State private var restAngle = 0.0
    @State private var playStart = Date.now
    @State private var frozenIdle = 0.0

    var body: some View {
        let radio = model.radio
        TimelineView(.animation(paused: !radio.isPlaying || reduceMotion || grab != nil)) { context in
            let idle = idleAngle(at: context.date)
            disc
                .rotationEffect(.degrees((grab == nil ? idle : frozenIdle) + spinDegrees))
                .overlay(alignment: .top) { bubble }
        }
        .frame(width: size, height: size)
        .offset(x: restingOffset(putAway: radio.isPutAway) + slide)
        // The record moves with the finger; every other change settles with a spring.
        .animation(grab == .label || reduceMotion ? nil : .spring(response: 0.42, dampingFraction: 0.78), value: radio.isPutAway)
        .animation(grab == .label ? nil : .spring(response: 0.42, dampingFraction: 0.78), value: slide)
        .onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { frame = $0 }
        .sensoryFeedback(.impact(weight: .light), trigger: pastThreshold)
        .onChange(of: radio.isPlaying) { _, playing in
            if playing { playStart = .now } else { restAngle = idleAngle(at: .now, playing: true) }
        }
        .onAppear { playStart = .now }
        .contentShape(Circle())
        .gesture(drag)
        .accessibilityElement()
        .accessibilityLabel("Record")
        .accessibilityHint("Drag around the edge to seek. Slide the label left to put the record away.")
        .accessibilityAdjustableAction { direction in
            Task { await radio.spin(degrees: direction == .increment ? 36 : -36) }
        }
    }

    /// Where the idle spin has the record: it keeps its angle across pauses and grabs.
    private func idleAngle(at date: Date, playing: Bool? = nil) -> Double {
        let turning = (playing ?? model.radio.isPlaying) && !reduceMotion
        guard turning else { return restAngle }
        let elapsed = date.timeIntervalSince(playStart) / VinylSeek.idleTurnDuration * 360
        return (restAngle + elapsed).truncatingRemainder(dividingBy: 360)
    }

    private var disc: some View {
        ZStack {
            Circle().fill(RadialGradient(colors: [Color(white: 0.16), Color(white: 0.05)], center: .center, startRadius: 4, endRadius: size / 2))
            ForEach(1..<6) { ring in
                Circle().stroke(Color.white.opacity(0.05), lineWidth: 1).padding(CGFloat(ring) * size * 0.07 + size * 0.14)
            }
            AsyncImage(url: track?.artworkURL) { $0.resizable().scaledToFill() } placeholder: { model.atmosphere.primary }
                .frame(width: size * 0.4, height: size * 0.4).clipShape(Circle())
                .overlay(Circle().fill(.black).frame(width: size * 0.04))
        }
        .clipShape(Circle())
        .shadow(color: .black.opacity(0.3), radius: 10, y: 6)
    }

    @ViewBuilder private var bubble: some View {
        if grab == .ring, spinDegrees != 0 {
            let delta = VinylSeek.seconds(forDegrees: spinDegrees)
            let target = VinylSeek.previewTarget(position: model.radio.position(at: .now), duration: model.radio.duration, delta: delta)
            Text(VinylSeek.bubbleText(delta: delta, target: target))
                .font(.caption.monospacedDigit().bold()).padding(.horizontal, 10).padding(.vertical, 5)
                .background(.thinMaterial, in: Capsule()).offset(y: -34)
        }
    }

    @State private var pastThreshold = false

    private var travel: CGFloat { VinylSleeve.travel(out: outOffset, side: size) }

    private func restingOffset(putAway: Bool) -> CGFloat { putAway ? VinylSleeve.putAwayOffset(side: size) : outOffset }

    private var drag: some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .global)
            .onChanged { value in
                let box = CGSize(width: size, height: size)
                // The record itself moves, so positions are read globally and mapped into its own box.
                func local(_ point: CGPoint) -> CGPoint { CGPoint(x: point.x - frame.minX + slide, y: point.y - frame.minY) }
                if grab == nil {
                    frozenIdle = idleAngle(at: .now)
                    grab = VinylSeek.isLabelGrab(local(value.startLocation), in: box) ? .label : .ring
                    lastAngle = VinylSeek.angle(of: local(value.startLocation), in: box)
                }
                switch grab {
                case .label:
                    let putAway = model.radio.isPutAway
                    slide = VinylSleeve.offset(forTranslation: value.translation.width, putAway: putAway, travel: travel)
                    pastThreshold = VinylSleeve.outcome(translation: value.translation.width, predicted: 0, putAway: putAway, travel: travel) != .none
                case .ring:
                    let angle = VinylSeek.angle(of: local(value.location), in: box)
                    spinDegrees += VinylSeek.wrappedDelta(from: lastAngle, to: angle) * 180 / .pi
                    lastAngle = angle
                case nil: break
                }
            }
            .onEnded { value in
                let radio = model.radio
                let mode = grab
                let degrees = spinDegrees
                withAnimation(reduceMotion ? nil : .spring(response: 0.42, dampingFraction: 0.78)) { slide = 0 }
                pastThreshold = false
                // Keep the angle the finger left it at; idle spin resumes from there.
                restAngle = (frozenIdle + (mode == .ring ? degrees : 0)).truncatingRemainder(dividingBy: 360)
                playStart = .now
                grab = nil; spinDegrees = 0
                switch mode {
                case .label:
                    switch VinylSleeve.outcome(translation: value.translation.width, predicted: value.predictedEndTranslation.width,
                                               putAway: radio.isPutAway, travel: travel) {
                    case .putAway: Task { await radio.putAway() }
                    case .resume: Task { await radio.comeBack() }
                    case .none: break
                    }
                case .ring:
                    if abs(degrees) >= VinylSeek.spinThresholdDegrees { Task { await radio.spin(degrees: degrees) } }
                case nil: break
                }
            }
    }
}
