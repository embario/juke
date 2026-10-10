import Foundation
import Observation

/// One thing on the "Your station:" line: a pulled record or a feeling.
enum NewStationPick: Identifiable, Hashable, Sendable {
    case record(Radio.Seed)
    case feeling(String)

    var id: String {
        switch self {
        case .record(let seed): "record:\(seed.id)"
        case .feeling(let feeling): "feeling:\(feeling)"
        }
    }

    /// Records by title, emoji as they are, phrases in curly quotes.
    var text: String {
        switch self {
        case .record(let seed): seed.title
        case .feeling(let feeling): NewStationFlow.isEmojiOnly(feeling) ? feeling : "“\(feeling)”"
        }
    }
}

/// State and rules for New Station: start with Records or Feelings, the other
/// step optional; up to three records (pulling a fourth swaps out the oldest);
/// any number of feelings, as emoji or short phrases.
@MainActor
@Observable
final class NewStationFlow {
    typealias Step = JukeCoordinator.NewStationDraft.Start

    static let maxRecords = 3
    /// Same limit as reactions; the server counts Unicode code points.
    nonisolated static let maxPhraseLength = Radio.ReactionsRequest.maxPhraseLength
    /// The server's `MAX_FEELINGS` (`backend/radio/serializers.py`).
    nonisolated static let maxFeelings = 12
    /// Emoji tokens offered on the Feelings step (the prototype's first 16).
    nonisolated static let vocabulary = ["😌", "🔥", "🌙", "☀️", "💃", "🥹", "🧘", "🚗", "🌧️", "✨", "☕", "🤘", "😭", "🥰", "😎", "🤯"]
    /// VoiceOver names for the emoji.
    nonisolated static let feelingNames: [String: String] = [
        "😌": "calm", "🔥": "fire", "🌙": "late night", "☀️": "sunny", "💃": "dancing", "🥹": "tender",
        "🧘": "centered", "🚗": "driving", "🌧️": "rainy", "✨": "magic", "☕": "slow morning", "🤘": "loud",
        "😭": "crying", "🥰": "in love", "😎": "cool", "🤯": "mind blown",
    ]

    /// The step the person started with; the other one is optional.
    private(set) var path: Step
    private(set) var step: Step
    /// Pulled records, oldest first.
    private(set) var seeds: [Radio.Seed]
    private(set) var feelings: [String]
    /// Feelings typed in "Or in your words", kept as tokens even when deselected.
    private(set) var customFeelings: [String] = []
    var wordsDraft = ""

    init(draft: JukeCoordinator.NewStationDraft = .init()) {
        path = draft.start
        step = draft.start
        seeds = Array(Self.unique(draft.seeds, by: { $0.id }).prefix(Self.maxRecords))
        feelings = Array(Self.unique(draft.feelings.compactMap(Self.normalizedFeeling), by: { $0 }).prefix(Self.maxFeelings))
        customFeelings = feelings.filter { !Self.vocabulary.contains($0) }
    }

    // MARK: Records

    func isPulled(_ seed: Radio.Seed) -> Bool { seeds.contains { $0.id == seed.id } }

    /// Pull or put back. With three pulled, pulling another swaps out the oldest.
    func togglePull(_ seed: Radio.Seed) {
        if let index = seeds.firstIndex(where: { $0.id == seed.id }) {
            seeds.remove(at: index)
            return
        }
        seeds.append(seed)
        if seeds.count > Self.maxRecords { seeds.removeFirst(seeds.count - Self.maxRecords) }
    }

    /// The pull button's VoiceOver label (no check glyph).
    func pullAccessibilityLabel(for seed: Radio.Seed?) -> String {
        guard let seed, isPulled(seed) else { return pullLabel(for: seed) }
        return "Pulled"
    }

    /// The crate's VoiceOver action for the front record.
    func pullActionName(for seed: Radio.Seed) -> String {
        isPulled(seed) ? "Put back this record" : pullLabel(for: seed)
    }

    func pullLabel(for seed: Radio.Seed?) -> String {
        guard let seed else { return "Pull this record" }
        if isPulled(seed) { return "Pulled ✓" }
        return seeds.count >= Self.maxRecords ? "Swap in this record" : "Pull this record"
    }

    // MARK: Feelings

    /// Emoji tokens, then the person's own words, then anything chosen elsewhere.
    var feelingTokens: [String] { Self.unique(Self.vocabulary + customFeelings + feelings, by: { $0 }) }

    func isChosen(_ feeling: String) -> Bool { feelings.contains(feeling) }

    /// At the server's limit: unchosen tokens and "Add" are disabled.
    var feelingsFull: Bool { feelings.count >= Self.maxFeelings }

    func toggleFeeling(_ feeling: String) {
        if let index = feelings.firstIndex(of: feeling) {
            feelings.remove(at: index)
        } else if !feelingsFull {
            feelings.append(feeling)
        }
    }

    /// Adds "Or in your words" as a feeling (a lone emoji stays an emoji).
    /// Returns what was added.
    @discardableResult
    func addWords() -> String? {
        guard let feeling = Self.normalizedFeeling(wordsDraft) else { return nil }
        if !feelings.contains(feeling) {
            guard !feelingsFull else { return nil }
            feelings.append(feeling)
        }
        if !Self.vocabulary.contains(feeling), !customFeelings.contains(feeling) { customFeelings.append(feeling) }
        wordsDraft = ""
        return feeling
    }

    // MARK: Your station

    var picks: [NewStationPick] { seeds.map(NewStationPick.record) + feelings.map(NewStationPick.feeling) }

    func remove(_ pick: NewStationPick) {
        switch pick {
        case .record(let seed): seeds.removeAll { $0.id == seed.id }
        case .feeling(let feeling): feelings.removeAll { $0 == feeling }
        }
    }

    var canStart: Bool { !seeds.isEmpty || !feelings.isEmpty }

    /// The name the server will give it (`"<first seed> Radio"` or `"<feelings> Radio"`).
    var stationName: String? {
        if let first = seeds.first { return "\(first.title) Radio" }
        guard !feelings.isEmpty else { return nil }
        return "\(feelings.prefix(3).joined(separator: " ")) Radio"
    }

    var startLabel: String { stationName.map { "Start \($0)" } ?? "Pick a record or a feeling" }

    var createRequest: Radio.CreateStationRequest {
        Radio.CreateStationRequest(name: nil, seeds: Array(seeds.prefix(Self.maxRecords)), feelings: feelings)
    }

    // MARK: Steps

    /// "Start with" tabs. Before anything is chosen, a tab also changes which
    /// step is the main one.
    func select(_ newStep: Step) {
        if seeds.isEmpty && feelings.isEmpty { path = newStep }
        step = newStep
    }

    var otherStep: Step { step == .records ? .feelings : .records }

    func goToOtherStep() { step = otherStep }

    /// The text link to the other step.
    var otherStepLabel: String {
        if path == step {
            return step == .records ? "Add a feeling (optional)" : "Add records (optional)"
        }
        return step == .records ? "Back to feelings" : "Back to records"
    }

    var stepLine: String {
        switch step {
        case .records: "Pull up to three records" + (path == .records ? ". Feelings are optional." : ". Your feelings are saved.")
        case .feelings: "Pick feelings, in emoji or words" + (path == .feelings ? ". Records are optional." : ". Your records are saved.")
        }
    }

    var feelingsHeading: String {
        guard let first = seeds.first else { return "What do you want to feel?" }
        return "How should \(first.title)\(seeds.count > 1 ? " & co." : "") feel?"
    }

    var previewCaption: String {
        if !seeds.isEmpty { return "Your records, plus what Juke will pull alongside them" }
        if !feelings.isEmpty { return "Juke will pull records that feel like \(feelings.prefix(3).map { NewStationPick.feeling($0).text }.joined(separator: " "))" }
        return "Pick a feeling and the crate fills up"
    }

    /// Up to seven tiles: pulled records first, then the crate's.
    func previewRecords(from crate: [Radio.CrateItem]) -> [Radio.Seed] {
        let extra = crate.map(\.seed).filter { !isPulled($0) }
        return Array(Self.unique(seeds + extra, by: { $0.id }).prefix(7))
    }

    // MARK: Helpers

    /// Trims, collapses spaces and limits to 40 code points (the server's
    /// measure) without splitting a character. Emoji and phrases are kept as
    /// typed, so "🔥🔥" stays "🔥🔥".
    nonisolated static func normalizedFeeling(_ text: String) -> String? {
        let collapsed = text.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        guard !collapsed.isEmpty else { return nil }
        let limited = limitedPhrase(collapsed).trimmingCharacters(in: .whitespaces)
        return limited.isEmpty ? nil : limited
    }

    /// The longest prefix of whole characters within `maxPhraseLength` code points.
    nonisolated static func limitedPhrase(_ text: String) -> String {
        var result = ""
        var scalars = 0
        for character in text {
            let count = character.unicodeScalars.count
            guard scalars + count <= maxPhraseLength else { break }
            result.append(character)
            scalars += count
        }
        return result
    }

    /// Only emoji (no letters or spaces): shown bare; anything else is a
    /// phrase and shown in quotes.
    nonisolated static func isEmojiOnly(_ text: String) -> Bool {
        !text.isEmpty && text.allSatisfy { isEmoji(String($0)) }
    }

    nonisolated static func isEmoji(_ text: String) -> Bool {
        text.unicodeScalars.contains { scalar in
            scalar.properties.isEmojiPresentation
                || (scalar.properties.isEmoji && scalar.value > 0x238C && !(0x30...0x39).contains(scalar.value))
        }
    }

    private static func unique<T, Key: Hashable>(_ values: [T], by key: (T) -> Key) -> [T] {
        var seen = Set<Key>()
        return values.filter { seen.insert(key($0)).inserted }
    }
}
