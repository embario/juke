import SwiftUI

/// A reusable, themed search input tailored for track lookup flows.
///
/// ## Usage
///
/// ```swift
/// @State private var query = ""
///
/// JukeKitTrackSearchField(
///     text: $query,
///     placeholder: "Search Spotify...",
///     onSubmit: { performSearch() },
///     onClear: { clearResults() }
/// )
/// ```
public struct JukeKitTrackSearchField: View {
    @Environment(\.jukeTheme) private var theme
    @Binding private var text: String
    private let placeholder: String
    private let onSubmit: (() -> Void)?
    private let onClear: (() -> Void)?

    public init(
        text: Binding<String>,
        placeholder: String = "Search tracks...",
        onSubmit: (() -> Void)? = nil,
        onClear: (() -> Void)? = nil
    ) {
        _text = text
        self.placeholder = placeholder
        self.onSubmit = onSubmit
        self.onClear = onClear
    }

    public var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "magnifyingglass")
                .foregroundColor(theme.muted)

            searchField

            if !text.isEmpty {
                Button {
                    text = ""
                    onClear?()
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(theme.muted)
                }
            }
        }
        .padding(.vertical, 12)
        .padding(.horizontal, 16)
        .background(theme.panelAlt.opacity(0.65))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(theme.border, lineWidth: 1)
        )
        .cornerRadius(14)
    }

    @ViewBuilder
    private var searchField: some View {
        #if canImport(UIKit)
        TextField(placeholder, text: $text)
            .foregroundColor(theme.text)
            .autocorrectionDisabled()
            .textInputAutocapitalization(.never)
            .onSubmit {
                onSubmit?()
            }
        #else
        TextField(placeholder, text: $text)
            .foregroundColor(theme.text)
            .onSubmit {
                onSubmit?()
            }
        #endif
    }
}

/// A reusable loading view for track-search flows.
public struct JukeKitTrackSearchLoadingView: View {
    @Environment(\.jukeTheme) private var theme
    @State private var pulse = false
    private let message: String

    public init(message: String = "Loading Tracks, please wait...") {
        self.message = message
    }

    public var body: some View {
        VStack(spacing: 12) {
            JukeKitSpinner()
            Text(message)
                .font(.subheadline.weight(.medium))
                .foregroundColor(theme.muted)
                .opacity(pulse ? 1.0 : 0.55)
                .animation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true), value: pulse)
        }
        .onAppear {
            pulse = true
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(message)
    }
}
