import SwiftUI

@MainActor
final class PlaybackBarViewModel: ObservableObject {
    @Published private(set) var state: PlaybackState?
    @Published private(set) var error: String?
    @Published private(set) var isBusy = false

    private let service: PlaybackService
    private let session: SessionStore
    private var progressTimer: Task<Void, Never>?
    private var pollTimer: Task<Void, Never>?

    init(session: SessionStore, service: PlaybackService = PlaybackService()) {
        self.session = session
        self.service = service
    }

    var isPlaying: Bool { state?.isPlaying ?? false }
    var canControl: Bool { session.token != nil }

    var track: PlaybackTrack? { state?.track }
    var progressMs: Int { state?.progressMs ?? 0 }
    var durationMs: Int { track?.durationMs ?? 0 }
    var progressPercent: Double {
        guard durationMs > 0 else { return 0 }
        return min(100, Double(progressMs) / Double(durationMs) * 100)
    }

    var artistLine: String {
        track?.artists?.compactMap { $0.name }.joined(separator: ", ") ?? "—"
    }

    func startPolling() {
        stopPolling()
        refresh()
        pollTimer = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 10_000_000_000) // 10s
                self?.refresh()
            }
        }
    }

    func stopPolling() {
        pollTimer?.cancel()
        pollTimer = nil
        progressTimer?.cancel()
        progressTimer = nil
    }

    private func refresh() {
        guard let token = session.token else {
            state = nil
            return
        }
        Task { [weak self] in
            do {
                let newState = try await self?.service.fetchState(
                    token: token,
                    provider: self?.state?.provider
                )
                self?.state = newState
                self?.error = nil
                self?.tickProgress()
            } catch {
                self?.error = error.localizedDescription
            }
        }
    }

    private func tickProgress() {
        progressTimer?.cancel()
        guard isPlaying else { return }
        progressTimer = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 1_000_000_000) // 1s
                guard let self else { return }
                guard self.isPlaying else { return }
                let current = self.progressMs
                let duration = self.durationMs
                let next = min(current + 1000, duration)
                // Mutate state in place to avoid full object replacement
                if var s = self.state {
                    self.state = PlaybackState(
                        provider: s.provider,
                        isPlaying: s.isPlaying,
                        progressMs: next,
                        track: s.track,
                        device: s.device
                    )
                }
            }
        }
    }

    func pause() async {
        guard let token = session.token else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            state = try await service.pause(token: token, provider: state?.provider, deviceId: state?.device?.id)
            error = nil
            tickProgress()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func resume() async {
        guard let token = session.token else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            state = try await service.resume(token: token, provider: state?.provider, deviceId: state?.device?.id)
            error = nil
            tickProgress()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func next() async {
        guard let token = session.token else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            state = try await service.next(token: token, provider: state?.provider, deviceId: state?.device?.id)
            error = nil
            tickProgress()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func previous() async {
        guard let token = session.token else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            state = try await service.previous(token: token, provider: state?.provider, deviceId: state?.device?.id)
            error = nil
            tickProgress()
        } catch {
            self.error = error.localizedDescription
        }
    }

    deinit {
        progressTimer?.cancel()
        pollTimer?.cancel()
    }
}

struct PlaybackBarView: View {
    @StateObject private var vm: PlaybackBarViewModel
    @EnvironmentObject private var session: SessionStore

    init(session: SessionStore) {
        _vm = StateObject(wrappedValue: PlaybackBarViewModel(session: session))
    }

    var body: some View {
        guard vm.canControl else { return AnyView(EmptyView()) }

        return AnyView(
            VStack(spacing: 0) {
                bar
            }
            .onAppear { vm.startPolling() }
            .onDisappear { vm.stopPolling() }
        )
    }

    private var bar: some View {
        VStack(spacing: 0) {
            // Progress track
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Rectangle()
                        .fill(JukePalette.panel)
                        .frame(height: 2)
                    Rectangle()
                        .fill(JukePalette.accent)
                        .frame(width: geo.size.width * vm.progressPercent / 100, height: 2)
                        .animation(.easeOut(duration: 0.3), value: vm.progressPercent)
                }
            }
            .frame(height: 2)

            HStack(alignment: .center, spacing: 12) {
                artworkView
                metaView
                Spacer(minLength: 0)
                controlButtons
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(
                JukePalette.panel
                    .shadow(color: .black.opacity(0.4), radius: 8, x: 0, y: -2)
            )
        }
    }

    private var artworkView: some View {
        Group {
            if let url = vm.track?.artworkUrl, let imageUrl = URL(string: url) {
                AsyncImage(url: imageUrl) { phase in
                    switch phase {
                    case .success(let image):
                        image.resizable().aspectRatio(contentMode: .fill)
                    default:
                        fallbackArtwork
                    }
                }
            } else {
                fallbackArtwork
            }
        }
        .frame(width: 40, height: 40)
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private var fallbackArtwork: some View {
        RoundedRectangle(cornerRadius: 6)
            .fill(JukePalette.panel.opacity(0.5))
            .overlay(
                Image(systemName: "music.note")
                    .foregroundColor(JukePalette.muted)
            )
    }

    private var metaView: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(vm.track?.name ?? "Nothing playing")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundColor(JukePalette.text)
                .lineLimit(1)
            Text(vm.artistLine)
                .font(.caption)
                .foregroundColor(JukePalette.muted)
                .lineLimit(1)
        }
        .frame(maxWidth: 140, alignment: .leading)
    }

    private var controlButtons: some View {
        HStack(spacing: 8) {
            controlButton(action: { await vm.previous() }, icon: "backward.fill", label: "Previous")
            controlButton(
                action: {
                    if vm.isPlaying { await vm.pause() } else { await vm.resume() }
                },
                icon: vm.isPlaying ? "pause.fill" : "play.fill",
                label: vm.isPlaying ? "Pause" : "Resume"
            )
            controlButton(action: { await vm.next() }, icon: "forward.fill", label: "Next")
        }
    }

    private func controlButton(action: @escaping () async -> Void, icon: String, label: String) -> some View {
        Button {
            Task { await action() }
        } label: {
            Image(systemName: icon)
                .foregroundColor(JukePalette.text)
                .font(.system(size: 14))
        }
        .accessibilityLabel(label)
        .disabled(vm.isBusy || !vm.canControl)
        .opacity(vm.isBusy ? 0.5 : 1)
    }

    private func formatDuration(_ ms: Int) -> String {
        let seconds = ms / 1000
        let mins = seconds / 60
        let secs = seconds % 60
        return String(format: "%d:%02d", mins, secs)
    }
}
