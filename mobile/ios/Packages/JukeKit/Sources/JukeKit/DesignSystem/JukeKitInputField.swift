import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// A themed text input field with label and optional error display.
///
/// Supports both regular text and secure (password) input.
///
/// ## Usage
///
/// ```swift
/// @State private var email = ""
///
/// JukeKitInputField(
///     label: "Email",
///     placeholder: "Enter your email",
///     text: $email,
///     keyboard: .emailAddress
/// )
/// ```
public struct JukeKitInputField: View {
    @Environment(\.jukeTheme) private var theme

    /// The type of input field.
    public enum FieldKind {
        case text
        case secure
    }

    private let label: String
    private let placeholder: String
    @Binding private var text: String
    private let kind: FieldKind
    #if canImport(UIKit)
    private let keyboard: UIKeyboardType
    private let textContentType: UITextContentType?
    private let autocapitalization: TextInputAutocapitalization
    #endif
    private let error: String?

    /// Creates a themed input field.
    /// - Parameters:
    ///   - label: The field label displayed above the input.
    ///   - placeholder: Placeholder text when empty.
    ///   - text: Binding to the text value.
    ///   - kind: Field type (text or secure). Defaults to `.text`.
    ///   - keyboard: Keyboard type. Defaults to `.default`.
    ///   - textContentType: Content type for autofill. Defaults to `nil`.
    ///   - autocapitalization: Autocapitalization behavior. Defaults to `.never`.
    ///   - error: Optional error message to display.
    #if canImport(UIKit)
    public init(
        label: String,
        placeholder: String,
        text: Binding<String>,
        kind: FieldKind = .text,
        keyboard: UIKeyboardType = .default,
        textContentType: UITextContentType? = nil,
        autocapitalization: TextInputAutocapitalization = .never,
        error: String? = nil
    ) {
        self.label = label
        self.placeholder = placeholder
        self._text = text
        self.kind = kind
        self.keyboard = keyboard
        self.textContentType = textContentType
        self.autocapitalization = autocapitalization
        self.error = error
    }
    #else
    public init(
        label: String,
        placeholder: String,
        text: Binding<String>,
        kind: FieldKind = .text,
        error: String? = nil
    ) {
        self.label = label
        self.placeholder = placeholder
        self._text = text
        self.kind = kind
        self.error = error
    }
    #endif

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label.uppercased())
                .font(.caption)
                .foregroundColor(theme.muted)
                .kerning(1.2)
            fieldWithModifiers
                .padding(.vertical, 14)
                .padding(.horizontal, 16)
                .background(theme.panelAlt.opacity(0.65))
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(error == nil ? theme.border : theme.error, lineWidth: 1)
                )
                .cornerRadius(16)
                .foregroundColor(theme.text)
            if let error {
                Text(error)
                    .font(.footnote)
                    .foregroundColor(theme.error)
            }
        }
    }

    @ViewBuilder
    private var fieldWithModifiers: some View {
        #if canImport(UIKit)
        field
            .textInputAutocapitalization(autocapitalization)
            .keyboardType(keyboard)
            .textContentType(textContentType)
        #else
        field
        #endif
    }

    @ViewBuilder
    private var field: some View {
        switch kind {
        case .text:
            TextField(placeholder, text: $text)
        case .secure:
            SecureField(placeholder, text: $text)
        }
    }
}
