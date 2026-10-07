import SwiftUI

/// The record. Drag the outer ring to turn it: one full turn seeks 14 s (past the
/// end moves on). Drag the centre label sideways to slide the record into
/// (left) or out of (right) the sleeve, which puts radio away or brings it back.
struct VinylDisc: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let track: Radio.Track?
    let size: CGFloat

    private enum Grab { case ring, label }
    @State private var grab: Grab?
    @State private var lastAngle = 0.0
    @State private var spinDegrees = 0.0
    @State private var slide: CGFloat = 0
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
                .offset(x: slide)
                .overlay(Circle().fill(.black).frame(width: size * 0.04).offset(x: slide))
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

    private var drag: some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .local)
            .onChanged { value in
                let box = CGSize(width: size, height: size)
                if grab == nil {
                    frozenIdle = idleAngle(at: .now)
                    grab = VinylSeek.isLabelGrab(value.startLocation, in: box) ? .label : .ring
                    lastAngle = VinylSeek.angle(of: value.startLocation, in: box)
                }
                switch grab {
                case .label:
                    slide = VinylLabelSlide.clamped(value.translation.width, putAway: model.radio.isPutAway)
                case .ring:
                    let angle = VinylSeek.angle(of: value.location, in: box)
                    spinDegrees += VinylSeek.wrappedDelta(from: lastAngle, to: angle) * 180 / .pi
                    lastAngle = angle
                case nil: break
                }
            }
            .onEnded { value in
                let radio = model.radio
                let mode = grab
                let degrees = spinDegrees
                withAnimation(.spring(duration: 0.35)) { slide = 0 }
                // Keep the angle the finger left it at; idle spin resumes from there.
                restAngle = (frozenIdle + (mode == .ring ? degrees : 0)).truncatingRemainder(dividingBy: 360)
                playStart = .now
                grab = nil; spinDegrees = 0
                switch mode {
                case .label:
                    switch VinylLabelSlide.outcome(dx: value.translation.width, putAway: radio.isPutAway) {
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
