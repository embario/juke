import SwiftUI

/// A themed selectable chip/tag button.
///
/// Displays a capsule-shaped button that indicates active/inactive state.
///
/// ## Usage
///
/// ```swift
/// JukeCoreChip(label: "Rock", isActive: selectedGenres.contains("Rock")) {
///     toggleGenre("Rock")
/// }
/// ```
public struct JukeCoreChip: View {
    @Environment(\.jukeTheme) private var theme

    private let label: String
    private let isActive: Bool
    private let color: Color?
    private let action: () -> Void

    /// Creates a themed chip.
    /// - Parameters:
    ///   - label: The chip label text.
    ///   - isActive: Whether the chip is in active state.
    ///   - color: Optional custom color. Defaults to theme accent.
    ///   - action: Callback when the chip is tapped.
    public init(
        label: String,
        isActive: Bool,
        color: Color? = nil,
        action: @escaping () -> Void
    ) {
        self.label = label
        self.isActive = isActive
        self.color = color
        self.action = action
    }

    private var chipColor: Color {
        color ?? theme.accent
    }

    public var body: some View {
        Button(action: action) {
            Text(label)
                .font(.subheadline)
                .padding(.vertical, 8)
                .padding(.horizontal, 16)
                .background(
                    Capsule(style: .continuous)
                        .fill(isActive ? chipColor.opacity(0.18) : Color.clear)
                )
                .overlay(
                    Capsule(style: .continuous)
                        .stroke(isActive ? chipColor : theme.border, lineWidth: 1)
                )
                .foregroundColor(isActive ? theme.text : theme.muted)
        }
        .buttonStyle(.plain)
    }
}
