import AppKit
import SwiftUI

/// Live state the dial reports to the card's status line.
struct DialActivity: Equatable {
    var holdingName: String?
    var holdingFrequency: Double?
    var openingNewStation = false
}

/// The FM dial (reference: `dialDown`, `enterHold`, `holdMove`,
/// `commitHold`, `tuneNearest`, `dialWheel`): drag with momentum and
/// rubber-band ends, scroll to step, click a station, flick past the end to
/// "+ New", press and hold a station to move it.
struct FMDialView: View {
    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    let stations: [Radio.Station]
    let tunedFrequency: Double
    let currentStationID: Radio.ID?
    let tunedStationID: Radio.ID?
    let showsCue: Bool
    let onTune: (Radio.ID) -> Void
    let onNewStation: () -> Void
    let onSwitchNow: () -> Void
    /// Station, target frequency, and which way to look for a free slot first.
    let onMove: (Radio.ID, Double, Int) async -> Double?
    @Binding var activity: DialActivity

    @State private var center: Double = FMDial.lowest
    @State private var dragDelta: CGFloat = 0
    @State private var press: Press?
    @State private var hold: Hold?
    @State private var holdTask: Task<Void, Never>?
    @State private var edgeTask: Task<Void, Never>?
    @State private var overrides: [Radio.ID: Double] = [:]
    @State private var newSelected = false
    @State private var wheel = WheelMonitor()
    @State private var width: CGFloat = 480
    @State private var didSync = false
    /// Latest inputs, read by the wheel monitor and delayed tasks (which hold
    /// an older copy of this view).
    @State private var liveTuned: Double = FMDial.lowest
    @State private var liveStations: [Radio.Station] = []

    private struct Press {
        var startX: CGFloat
        var lastX: CGFloat
        var time: Date
        var velocity: Double = 0
        var moved = false
        var mark: FMDial.Mark?
    }

    private struct Hold: Equatable {
        var id: Radio.ID
        var frequency: Double
        var view: Double
        var grab: Double
        var pointerX: CGFloat
    }

    var body: some View {
        HStack(spacing: 4) {
            arrow("chevron.left", label: "Previous station") { step(-1) }
            dial
            arrow("chevron.right", label: "Next station") { step(1) }
        }
        .onAppear {
            if !didSync { center = tunedFrequency; didSync = true }
            liveTuned = tunedFrequency
            liveStations = stations
            wheel.install { delta in step(delta) }
        }
        .onDisappear { wheel.remove(); holdTask?.cancel(); edgeTask?.cancel() }
        .onChange(of: tunedFrequency) { _, value in
            liveTuned = value
            guard press == nil, hold == nil, !newSelected else { return }
            withAnimation(reduceMotion ? nil : JukeMotion.easeOutSoft(FMDial.tuneDuration(distance: abs(value - center)))) { center = value }
        }
        .onChange(of: stations) { _, value in
            overrides = [:]
            liveStations = value
        }
    }

    private func arrow(_ symbol: String, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(theme.sub.color)
                .frame(width: 36, height: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }

    // MARK: Dial

    private var displayCenter: Double { hold?.view ?? center }

    private var dial: some View {
        GeometryReader { proxy in
            let offset = FMDial.bandOffset(center: displayCenter, dragDelta: dragDelta)
            ZStack(alignment: .topLeading) {
                band
                    .offset(x: proxy.size.width / 2 + offset)
                Rectangle()
                    .fill(theme.accent.color)
                    .frame(width: 2, height: 88)
                    .offset(x: proxy.size.width / 2 - 1)
                    .allowsHitTesting(false)
                if showsCue, hold == nil, press?.moved != true, !newSelected {
                    Button(action: onSwitchNow) {
                        Image(systemName: "play.fill")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundStyle(theme.onAccent.color)
                            .frame(width: 36, height: 36)
                            .background(theme.accent.color, in: Circle())
                            .shadow(color: .black.opacity(0.25), radius: 8, y: 6)
                            .contentShape(Circle())
                    }
                    .buttonStyle(.plain)
                    .offset(x: proxy.size.width / 2 + 68, y: 36)
                    .help("Play now")
                    .accessibilityLabel("Play \(stationName(tunedStationID)) now")
                    .accessibilityIdentifier("radio.dial.playNow")
                    .transition(.scale.combined(with: .opacity))
                }
            }
            .frame(width: proxy.size.width, height: 88, alignment: .topLeading)
            .contentShape(Rectangle())
            .gesture(dragGesture(width: proxy.size.width))
            .onAppear { width = proxy.size.width }
            .onChange(of: proxy.size.width) { _, value in width = value }
        }
        .frame(height: 88)
        .background(theme.well.color)
        .clipShape(RoundedRectangle(cornerRadius: JukeRadius.well, style: .continuous))
        .onContinuousHover { phase in
            if case .active = phase { wheel.isHovering = true } else { wheel.isHovering = false }
        }
        .help("Drag to tune. Press and hold a station to move it.")
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("FM dial")
        .accessibilityValue(accessibilityValue)
        .accessibilityIdentifier("radio.dial")
        .accessibilityAdjustableAction { direction in
            switch direction {
            case .increment: step(1)
            case .decrement: step(-1)
            @unknown default: break
            }
        }
        .accessibilityActions {
            ForEach(stations) { station in
                Button("Tune to \(station.name)") { tune(to: .station(station.id), frequency: station.frequency) }
            }
            if let id = tunedStationID, let station = stations.first(where: { $0.id == id }) {
                Button("Move \(station.name) up the dial") { Task { _ = await onMove(id, station.frequency + FMDial.minimumSpacing, 1) } }
                Button("Move \(station.name) down the dial") { Task { _ = await onMove(id, station.frequency - FMDial.minimumSpacing, -1) } }
            }
            if showsCue { Button("Play the tuned station now", action: onSwitchNow) }
            Button("New station", action: onNewStation)
        }
    }

    private var accessibilityValue: String {
        if newSelected { return "New station" }
        guard let id = tunedStationID, let station = stations.first(where: { $0.id == id }) else { return "Not tuned" }
        return "Tuned to \(station.name), \(station.frequencyLabel) FM" + (showsCue ? ", plays after this song" : "")
    }

    private var band: some View {
        ZStack(alignment: .topLeading) {
            Canvas { canvas, size in
                var x: CGFloat = 0
                let step = FMDial.pointsPerMHz * 0.2
                while x <= size.width {
                    canvas.fill(Path(CGRect(x: x, y: 0, width: 1, height: 11)), with: .color(theme.tick))
                    x += step
                }
            }
            .frame(width: FMDial.bandWidth, height: 11)
            ForEach(Array(stride(from: 88, through: 108, by: 2)), id: \.self) { mhz in
                Text("\(mhz)")
                    .font(JukeFont.mono(9))
                    .foregroundStyle(theme.sub.color)
                    .frame(width: 30)
                    .offset(x: FMDial.x(for: Double(mhz)) - 15, y: 11)
            }
            ForEach(stations) { station in
                stationTile(station)
            }
            newTile
        }
        .frame(width: FMDial.bandWidth, height: 88, alignment: .topLeading)
        .accessibilityHidden(true)
    }

    private func frequency(of station: Radio.Station) -> Double {
        if let hold, hold.id == station.id { return hold.frequency }
        return overrides[station.id] ?? station.frequency
    }

    private func stationTile(_ station: Radio.Station) -> some View {
        let held = hold?.id == station.id
        let f = frequency(of: station)
        let tuned = abs(station.frequency - displayTuned) < 0.01 && !newSelected
        return VStack(spacing: 2) {
            Text(String(format: "%.1f FM", f))
                .font(JukeFont.mono(10))
                .tracking(0.5)
                .foregroundStyle(held ? theme.accent.color : (tuned ? theme.ink.color : theme.sub.color))
            Text(station.name)
                .font(JukeFont.body(13, weight: tuned || held ? .heavy : .medium))
                .foregroundStyle(tuned || held ? theme.ink.color : theme.sub.color)
                .lineLimit(1)
            HStack(spacing: 3) {
                ForEach(Array(station.thumbnailURLs.prefix(3).enumerated()), id: \.offset) { _, url in
                    RadioArtwork(url: url, cornerRadius: 3).frame(width: 14, height: 14)
                }
            }
            .frame(minHeight: 14)
        }
        .padding(.vertical, 4)
        .frame(width: FMDial.itemWidth)
        .frame(minHeight: 58)
        .background(held ? theme.card.color : .clear, in: RoundedRectangle(cornerRadius: JukeRadius.tile, style: .continuous))
        .shadow(color: held ? theme.liftShadow.color : .clear, radius: theme.liftShadow.radius, y: theme.liftShadow.y)
        .scaleEffect(held ? 1.1 : 1)
        .offset(x: FMDial.x(for: f) - FMDial.itemWidth / 2, y: 24 + (held ? -12 : 0))
        .zIndex(held ? 20 : 1)
        .animation(reduceMotion ? nil : (held ? .easeOut(duration: 0.2) : JukeMotion.easeOutSoft(0.45)), value: f)
        .animation(reduceMotion ? nil : JukeMotion.easeOutSoft(0.3), value: held)
    }

    private var newTile: some View {
        VStack(spacing: 2) {
            Text("+ ADD").font(JukeFont.mono(10)).tracking(0.5).foregroundStyle(theme.accent.color)
            Text("New station").font(JukeFont.body(13, weight: .bold)).foregroundStyle(theme.ink.color)
        }
        .padding(.vertical, 4)
        .frame(width: FMDial.itemWidth, height: 58, alignment: .top)
        .offset(x: FMDial.x(for: FMDial.newSlot) - FMDial.itemWidth / 2, y: 24)
    }

    /// The frequency the needle settles on (excluding live drag).
    private var displayTuned: Double { tunedFrequency }

    private func stationName(_ id: Radio.ID?) -> String {
        stations.first { $0.id == id }?.name ?? "the station"
    }

    // MARK: Gestures

    private func mark(at location: CGPoint, width: CGFloat) -> FMDial.Mark? {
        guard (24...82).contains(location.y) else { return nil }
        let bandX = location.x - (width / 2 + FMDial.bandOffset(center: displayCenter, dragDelta: 0))
        for station in stations where abs(FMDial.x(for: frequency(of: station)) - bandX) <= FMDial.itemWidth / 2 {
            return .station(station.id)
        }
        if abs(FMDial.x(for: FMDial.newSlot) - bandX) <= FMDial.itemWidth / 2 { return .newStation }
        return nil
    }

    private func dragGesture(width: CGFloat) -> some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .local)
            .onChanged { value in
                if press == nil {
                    let mark = mark(at: value.startLocation, width: width)
                    press = Press(startX: value.startLocation.x, lastX: value.startLocation.x, time: .now, mark: mark)
                    holdTask?.cancel()
                    if case .station(let id) = mark {
                        holdTask = Task { @MainActor in
                            try? await Task.sleep(for: RadioGesture.holdDelay)
                            guard !Task.isCancelled, press?.moved == false else { return }
                            enterHold(id, pointerX: press?.lastX ?? value.startLocation.x, width: width)
                        }
                    }
                }
                guard var current = press else { return }
                let x = value.location.x
                if hold != nil {
                    current.lastX = x
                    press = current
                    holdMove(pointerX: x, width: width)
                    return
                }
                let now = Date()
                current.velocity = RadioGesture.smoothedVelocity(previous: current.velocity, delta: Double(x - current.lastX),
                                                                 dtMilliseconds: now.timeIntervalSince(current.time) * 1000, weight: 0.75)
                current.lastX = x
                current.time = now
                if abs(x - current.startX) > FMDial.dragThreshold { current.moved = true; holdTask?.cancel() }
                press = current
                if current.moved { dragDelta = x - current.startX }
            }
            .onEnded { _ in
                holdTask?.cancel()
                guard let ended = press else { return }
                press = nil
                if hold != nil { commitHold(); return }
                if ended.moved {
                    let target = FMDial.releaseCenter(tuned: center, dragDelta: ended.lastX - ended.startX, velocity: ended.velocity,
                                                      sinceLastMove: Date().timeIntervalSince(ended.time))
                    let slot = FMDial.nearest(to: target, in: FMDial.slots(stations))
                    let current = center - Double(dragDelta / FMDial.pointsPerMHz)
                    if let slot { tune(to: slot.mark, frequency: slot.frequency, from: current) }
                    return
                }
                switch ended.mark {
                case .station(let id): tune(to: .station(id), frequency: stations.first { $0.id == id }?.frequency ?? center)
                case .newStation: tune(to: .newStation, frequency: FMDial.newSlot)
                case nil: break
                }
            }
    }

    private func tune(to mark: FMDial.Mark, frequency: Double, from start: Double? = nil) {
        let origin = start ?? center
        let duration = FMDial.tuneDuration(distance: abs(frequency - origin))
        var instant = Transaction()
        instant.disablesAnimations = true
        withTransaction(instant) {
            center = origin
            dragDelta = 0
        }
        withAnimation(reduceMotion ? nil : JukeMotion.easeOutSoft(duration)) { center = frequency }
        switch mark {
        case .station(let id):
            newSelected = false
            activity.openingNewStation = false
            onTune(id)
        case .newStation:
            newSelected = true
            activity.openingNewStation = true
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(reduceMotion ? 0.15 : duration + 0.15))
                onNewStation()
                newSelected = false
                activity.openingNewStation = false
                center = liveTuned
            }
        }
    }

    private func step(_ direction: Int) {
        let slots = FMDial.slots(liveStations)
        guard let slot = FMDial.step(from: newSelected ? FMDial.newSlot : liveTuned, direction: direction, in: slots) else { return }
        tune(to: slot.mark, frequency: slot.frequency)
    }

    // MARK: Hold to move

    private func enterHold(_ id: Radio.ID, pointerX: CGFloat, width: CGFloat) {
        guard let station = stations.first(where: { $0.id == id }) else { return }
        let view = center
        let grab = FMDial.holdGrab(pointerFromCenter: pointerX - width / 2, stationFrequency: frequency(of: station), view: view)
        NSHapticFeedbackManager.defaultPerformer.perform(.alignment, performanceTime: .now)
        dragDelta = 0
        hold = Hold(id: id, frequency: frequency(of: station), view: view, grab: grab, pointerX: pointerX)
        activity.holdingName = station.name
        activity.holdingFrequency = hold?.frequency
    }

    private func holdMove(pointerX: CGFloat, width: CGFloat) {
        guard var current = hold else { return }
        current.pointerX = pointerX
        current.frequency = FMDial.holdFrequency(view: current.view, pointerFromCenter: pointerX - width / 2, grab: current.grab)
        hold = current
        activity.holdingFrequency = current.frequency
        let direction = FMDial.edgeDirection(pointerX: pointerX, width: width)
        edgeTask?.cancel()
        guard direction != 0 else { return }
        edgeTask = Task { @MainActor in
            while !Task.isCancelled, var moving = hold {
                withAnimation(.linear(duration: 0.12)) {
                    moving.view = FMDial.scrolledView(moving.view, direction: direction)
                    moving.frequency = FMDial.holdFrequency(view: moving.view, pointerFromCenter: moving.pointerX - width / 2, grab: moving.grab)
                    hold = moving
                }
                activity.holdingFrequency = moving.frequency
                try? await Task.sleep(for: .milliseconds(16))
            }
        }
    }

    private func commitHold() {
        edgeTask?.cancel()
        guard let held = hold else { return }
        let others = stations.filter { $0.id != held.id }.map(\.frequency)
        let original = stations.first { $0.id == held.id }?.frequency ?? held.frequency
        let direction = held.frequency >= original ? 1 : -1
        let proposal = FMDial.freeSlot(near: held.frequency, others: others, preferring: direction)
        overrides[held.id] = proposal
        withAnimation(reduceMotion ? nil : JukeMotion.easeOutSoft(0.52)) {
            hold = nil
            center = tunedFrequency
        }
        activity.holdingName = nil
        activity.holdingFrequency = nil
        Task { @MainActor in
            let final = await onMove(held.id, proposal, direction)
            if let final { overrides[held.id] = final } else { overrides[held.id] = nil }
        }
    }
}

/// Turns trackpad/scroll-wheel movement over the dial into station steps.
@MainActor
final class WheelMonitor {
    var isHovering = false
    private var monitor: Any?
    private var accumulated: CGFloat = 0

    func install(_ step: @escaping @MainActor (Int) -> Void) {
        remove()
        monitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { [weak self] event in
            let dx = abs(event.scrollingDeltaX) > abs(event.scrollingDeltaY) ? event.scrollingDeltaX : event.scrollingDeltaY
            let scale: CGFloat = event.hasPreciseScrollingDeltas ? 1 : 12
            let consumed = MainActor.assumeIsolated { () -> Bool in
                guard let self, self.isHovering else { return false }
                // Natural scrolling: moving content left tunes up.
                self.accumulated -= dx * scale
                if abs(self.accumulated) >= FMDial.wheelStep {
                    let direction = self.accumulated > 0 ? 1 : -1
                    self.accumulated = 0
                    step(direction)
                }
                return true
            }
            return consumed ? nil : event
        }
    }

    func remove() {
        if let monitor { NSEvent.removeMonitor(monitor) }
        monitor = nil
        accumulated = 0
    }
}
