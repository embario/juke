import Foundation

/// The pages of the New Station wizard and the rules between them.
///
/// `start` asks how to begin (feelings or records); `first` and `second` are the
/// chosen path and the other, optional, step; `finish` names the station.
enum NewStationPage: Int, CaseIterable, Comparable, Sendable {
    case start, first, second, finish

    static func < (lhs: Self, rhs: Self) -> Bool { lhs.rawValue < rhs.rawValue }

    /// Which content a page shows, given the path chosen on the first page.
    func step(path: NewStationFlow.Step) -> NewStationFlow.Step? {
        switch self {
        case .first: path
        case .second: path == .records ? .feelings : .records
        case .start, .finish: nil
        }
    }

    var next: NewStationPage? { Self(rawValue: rawValue + 1) }
    var previous: NewStationPage? { Self(rawValue: rawValue - 1) }
}

@MainActor
enum NewStationWizard {
    /// Where the wizard opens: a draft that already has records or feelings (for
    /// example "Pull more records" on a station) skips the question.
    static func initialPage(for draft: JukeCoordinator.NewStationDraft) -> NewStationPage {
        draft.seeds.isEmpty && draft.feelings.isEmpty ? .start : .first
    }

    /// The first page needs something chosen before Next; the optional second page never blocks.
    static func canAdvance(from page: NewStationPage, flow: NewStationFlow) -> Bool {
        switch page {
        case .start: true
        case .first:
            switch page.step(path: flow.path) {
            case .records: !flow.seeds.isEmpty
            case .feelings: !flow.feelings.isEmpty
            case nil: true
            }
        case .second: true
        case .finish: flow.canStart
        }
    }

    /// "Skip" when the optional page has nothing chosen, otherwise "Next".
    static func advanceLabel(from page: NewStationPage, flow: NewStationFlow) -> String {
        switch page {
        case .second:
            page.step(path: flow.path) == .records ? (flow.seeds.isEmpty ? "Skip" : "Next") : (flow.feelings.isEmpty ? "Skip" : "Next")
        default: "Next"
        }
    }

    /// The server has no description field, so the description joins the station as one
    /// more feeling phrase (at most the server's 40 code points, and 12 feelings).
    static func feelings(_ chosen: [String], description: String) -> [String] {
        var result = chosen
        if let phrase = NewStationFlow.normalizedFeeling(description), !result.contains(phrase),
           result.count < NewStationFlow.maxFeelings {
            result.append(phrase)
        }
        return result
    }

    /// Trimmed name, or `nil` so the server picks "<first seed> Radio".
    static func name(_ text: String) -> String? {
        let trimmed = text.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        return trimmed.isEmpty ? nil : String(trimmed.prefix(80))
    }
}
