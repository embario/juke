import SwiftUI

/// A themed loading spinner with animated dots.
///
/// Displays three dots that pulse in sequence.
///
/// ## Usage
///
/// ```swift
/// if isLoading {
///     JukeKitSpinner()
/// }
/// ```
public struct JukeKitSpinner: View {
    @Environment(\.jukeTheme) private var theme
    @State private var animate = false

    public init() {}

    public var body: some View {
        HStack(spacing: 8) {
            ForEach(0..<3, id: \.self) { index in
                Circle()
                    .fill(theme.accent)
                    .frame(width: 10, height: 10)
                    .scaleEffect(animate ? 1 : 0.6)
                    .opacity(animate ? 1 : 0.4)
                    .animation(
                        Animation.easeInOut(duration: 0.8)
                            .repeatForever()
                            .delay(Double(index) * 0.15),
                        value: animate
                    )
            }
        }
        .onAppear { animate = true }
        .accessibilityLabel("Loading")
    }
}
