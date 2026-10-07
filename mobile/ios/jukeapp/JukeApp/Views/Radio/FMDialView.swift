import SwiftUI

/// The FM dial: drag the band under the needle; it settles on the nearest
/// station (or "+ New" past the top of the band). Tap a station to tune it.
struct FMDialView: View {
    @Environment(VibeAppModel.self) private var model
    @State private var center = 88.1
    @State private var dragDelta: CGFloat = 0
    @State private var dragging = false
    @State private var lastTick = 0
    /// A station picked up by press-and-hold, and where it would land.
    @State private var holding: (id: Radio.ID, frequency: Double)?

    var body: some View {
        let radio = model.radio
        VStack(spacing: 6) {
            GeometryReader { geo in
                ZStack(alignment: .topLeading) {
                    ticks
                    ForEach(radio.stations) { station in
                        stationMark(station)
                            .position(x: FMDial.x(for: holding?.id == station.id ? holding!.frequency : station.frequency), y: holding?.id == station.id ? 30 : 38)
                    }
                    newMark.position(x: FMDial.x(for: FMDial.newSlot), y: 38)
                }
                .frame(width: FMDial.bandWidth, height: 80, alignment: .topLeading)
                .offset(x: geo.size.width / 2 + FMDial.bandOffset(center: center, dragDelta: dragDelta))
                .frame(width: geo.size.width, height: 80, alignment: .leading)
                .overlay(alignment: .center) { Capsule().fill(Color.red.opacity(0.85)).frame(width: 2, height: 80) }
                .contentShape(Rectangle())
                .gesture(DragGesture(minimumDistance: FMDial.dragThreshold)
                    .onChanged { value in dragging = true; dragDelta = value.translation.width; tick() }
                    .onEnded { value in settle(value) })
            }
            .frame(height: 80).clipped()
            .background(Color.secondary.opacity(0.10), in: RoundedRectangle(cornerRadius: 14))
            .sensoryFeedback(.selection, trigger: lastTick)
            Text(readout).font(.footnote.monospaced()).foregroundStyle(.secondary)
        }
        .onAppear { syncToTuned() }
        .onChange(of: radio.tunedStation?.id) { _, _ in if !dragging { withAnimation(.easeOut(duration: 0.4)) { syncToTuned() } } }
        .onChange(of: radio.stations.count) { _, _ in if !dragging { syncToTuned() } }
        .accessibilityElement(children: .contain)
    }

    private var readout: String {
        let radio = model.radio
        guard let tuned = radio.tunedStation else { return "—" }
        return "\(tuned.name) · FM \(tuned.frequencyLabel)"
    }

    private var liveCenter: Double { center - Double(dragDelta) / Double(FMDial.pointsPerMHz) }

    private func tick() {
        let value = Int((liveCenter * 5).rounded())
        if value != lastTick { lastTick = value }
    }

    private func syncToTuned() {
        if let frequency = model.radio.tunedStation?.frequency { center = frequency }
    }

    private func settle(_ value: DragGesture.Value) {
        let velocity = Double(value.velocity.width) / 1000
        let target = FMDial.releaseCenter(tuned: center, dragDelta: value.translation.width, velocity: velocity, sinceLastMove: 0)
        let slots = FMDial.slots(model.radio.stations)
        let slot = FMDial.nearest(to: target, in: slots)
        let from = center
        center = from - Double(value.translation.width) / Double(FMDial.pointsPerMHz)
        dragDelta = 0
        guard let slot else { dragging = false; return }
        let distance = abs(slot.frequency - center)
        withAnimation(.easeOut(duration: FMDial.tuneDuration(distance: distance))) { center = slot.frequency }
        dragging = false
        switch slot.mark {
        case .station(let id): Task { await model.radio.tune(to: id) }
        case .newStation:
            model.coordinator.openNewStation()
            withAnimation { syncToTuned() }
        }
    }

    private var ticks: some View {
        Canvas { context, size in
            var frequency = 88.0
            while frequency <= 108.0 {
                let x = FMDial.x(for: frequency)
                let major = Int(frequency.rounded()) % 2 == 0 && abs(frequency - frequency.rounded()) < 0.01
                let path = Path { $0.move(to: CGPoint(x: x, y: 64)); $0.addLine(to: CGPoint(x: x, y: major ? 48 : 56)) }
                context.stroke(path, with: .color(.secondary.opacity(major ? 0.7 : 0.35)), lineWidth: 1)
                if major { context.draw(Text("\(Int(frequency))").font(.system(size: 9, design: .monospaced)).foregroundStyle(.secondary), at: CGPoint(x: x, y: 72)) }
                frequency += 0.5
            }
        }
        .frame(width: FMDial.bandWidth, height: 80)
        .allowsHitTesting(false)
    }

    private func stationMark(_ station: Radio.Station) -> some View {
        let tuned = station.id == model.radio.tunedStation?.id
        let lifted = holding?.id == station.id
        return VStack(spacing: 2) {
            Text(station.name).font(.caption.weight(.semibold)).lineLimit(1)
            Text(String(format: "%.1f", lifted ? holding!.frequency : station.frequency)).font(.system(size: 10, design: .monospaced)).foregroundStyle(.secondary)
        }
        .padding(.horizontal, 8).padding(.vertical, 5).frame(width: FMDial.itemWidth - 12)
        .background(tuned || lifted ? model.atmosphere.primary.opacity(0.3) : Color.secondary.opacity(0.15), in: RoundedRectangle(cornerRadius: 9))
        .scaleEffect(lifted ? 1.08 : 1)
        .contentShape(Rectangle())
        .onTapGesture { Task { await model.radio.tune(to: station.id) } }
        .gesture(
            LongPressGesture(minimumDuration: RadioGesture.holdDelay.seconds)
                .sequenced(before: DragGesture(minimumDistance: 0))
                .onChanged { phase in
                    guard case .second(true, let drag) = phase else { return }
                    let dx = drag?.translation.width ?? 0
                    let target = FMDial.snap(station.frequency + Double(dx) / Double(FMDial.pointsPerMHz))
                    if holding?.id != station.id { lastTick += 1 }
                    holding = (station.id, target)
                }
                .onEnded { phase in
                    guard let held = holding, held.id == station.id else { holding = nil; return }
                    let direction = held.frequency >= station.frequency ? 1 : -1
                    holding = nil
                    Task { await model.radio.moveStation(station.id, to: held.frequency, preferring: direction) }
                }
        )
        .accessibilityAction(named: "Move up the dial") { Task { await model.radio.moveStation(station.id, to: station.frequency + 2.2, preferring: 1) } }
        .accessibilityAction(named: "Move down the dial") { Task { await model.radio.moveStation(station.id, to: station.frequency - 2.2, preferring: -1) } }
        .accessibilityLabel("\(station.name), \(station.frequencyLabel) FM")
        .accessibilityAddTraits(.isButton)
    }

    private var newMark: some View {
        Button { model.coordinator.openNewStation() } label: {
            Label("New", systemImage: "plus").font(.caption.weight(.semibold)).padding(8)
                .background(Color.secondary.opacity(0.15), in: RoundedRectangle(cornerRadius: 9))
        }.buttonStyle(.plain)
    }
}

private extension Duration {
    var seconds: TimeInterval { TimeInterval(components.seconds) + TimeInterval(components.attoseconds) / 1e18 }
}
