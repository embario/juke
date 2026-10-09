import Foundation

enum ChatComposer {
    static func canSend(draft: String, isSending: Bool) -> Bool {
        !isSending && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}
