import SwiftUI

/// Lightweight model for transient in-app notifications.
public struct JukeKitFlashMessage: Identifiable {
    public let id = UUID()
    public let text: String
    public let variant: JukeKitStatusBanner.Variant
}

/// Coordinates transient status messages shown in a top overlay.
@MainActor
public final class JukeKitFlashCenter: ObservableObject {
    @Published public private(set) var message: JukeKitFlashMessage?
    private var dismissTask: Task<Void, Never>?

    public init() {}

    deinit {
        dismissTask?.cancel()
    }

    public func show(
        _ text: String,
        variant: JukeKitStatusBanner.Variant = .info,
        duration: TimeInterval = 2.5
    ) {
        let message = JukeKitFlashMessage(text: text, variant: variant)
        withAnimation {
            self.message = message
        }

        dismissTask?.cancel()
        dismissTask = Task { [weak self] in
            let clampedDuration = max(duration, 0)
            if clampedDuration > 0 {
                try? await Task.sleep(nanoseconds: UInt64(clampedDuration * 1_000_000_000))
            }
            guard !Task.isCancelled else { return }
            await MainActor.run {
                self?.clear(id: message.id)
            }
        }
    }

    public func clear() {
        dismissTask?.cancel()
        withAnimation {
            message = nil
        }
    }

    private func clear(id: UUID) {
        guard message?.id == id else { return }
        withAnimation {
            message = nil
        }
    }
}

private struct JukeKitFlashOverlayModifier: ViewModifier {
    @ObservedObject var center: JukeKitFlashCenter
    let horizontalPadding: CGFloat
    let topPadding: CGFloat

    func body(content: Content) -> some View {
        content
            .overlay {
                GeometryReader { proxy in
                    VStack(spacing: 0) {
                        if let message = center.message {
                            JukeKitStatusBanner(message: message.text, variant: message.variant)
                                .padding(.horizontal, horizontalPadding)
                                .padding(.top, proxy.safeAreaInsets.top + topPadding)
                                .transition(.move(edge: .top).combined(with: .opacity))
                        }
                        Spacer(minLength: 0)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .zIndex(10_000)
                    .allowsHitTesting(false)
                }
                .ignoresSafeArea()
            }
            .animation(.easeInOut(duration: 0.2), value: center.message?.id)
    }
}

public extension View {
    /// Presents transient messages managed by the supplied flash center.
    func jukeFlashOverlay(
        _ center: JukeKitFlashCenter,
        horizontalPadding: CGFloat = 20,
        topPadding: CGFloat = 10
    ) -> some View {
        modifier(
            JukeKitFlashOverlayModifier(
                center: center,
                horizontalPadding: horizontalPadding,
                topPadding: topPadding
            )
        )
    }
}
