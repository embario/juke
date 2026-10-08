import Foundation
import ImageIO

/// The rules of the New Memory journey: photos, a song, the story, a preview, done.
/// Pure, so the order, copy and validation are unit-tested. Copy follows the Mac composer.
struct MemoryJourneyFlow: Equatable {
    enum Step: Int, CaseIterable, Sendable { case photo, song, story, review, complete }

    /// Starting with the song when music is already playing puts the music-first hook up front.
    private(set) var order: [Step]
    private(set) var step: Step
    private(set) var furthest = 0
    var promptIndex = 0

    init(startWithSong: Bool = false) {
        order = startWithSong ? [.song, .photo, .story, .review] : [.photo, .song, .story, .review]
        step = order[0]
    }

    var index: Int { order.firstIndex(of: step) ?? order.count }
    var isFirst: Bool { index == 0 }
    var showsProgress: Bool { step != .complete }

    /// Advances (unlocking the next dot). From the review the caller saves first, then calls `complete()`.
    mutating func next() {
        guard let target = order.firstIndex(of: step).map({ $0 + 1 }) else { return }
        if target < order.count { step = order[target]; furthest = max(furthest, target) }
    }

    mutating func back() {
        guard index > 0 else { return }
        step = order[index - 1]
    }

    /// Only steps already reached can be jumped to.
    mutating func jump(to target: Step) {
        guard let position = order.firstIndex(of: target), position <= furthest else { return }
        step = target
    }

    mutating func complete() { step = .complete }

    // MARK: Copy

    func title(draftHasSong: Bool, nowPlaying: Bool, question: String) -> String {
        switch step {
        case .photo: order.first == .song && draftHasSong ? "Now, where does it take you?" : "Find a little time machine."
        case .song: order.first == .song && nowPlaying && !draftHasSong ? "Is this the one?" : "What was the soundtrack?"
        case .story: question
        case .review: "A moment, made yours."
        case .complete: "Tucked into your soundtrack."
        }
    }

    func subtitle(draftHasSong: Bool, nowPlaying: Bool, storyContext: String) -> String {
        switch step {
        case .photo: "Choose the pictures that go with it."
        case .song: order.first == .song && nowPlaying && !draftHasSong ? "It’s playing right now. Or find any song that takes you back." : "One song can bring it all back."
        case .story: storyContext.isEmpty ? "A few words, if you feel like it." : storyContext
        case .review: "Tap anything on the card to change it."
        case .complete: "It’s waiting in your memories, whenever you want to return."
        }
    }

    func primaryLabel(hasPhotos: Bool, hasSong: Bool) -> String {
        switch step {
        case .photo: hasPhotos ? "Bring these along" : "Continue without photos"
        case .song: hasSong ? "Keep going" : "Continue without a song"
        case .story: "See your memory"
        case .review: "Keep this memory"
        case .complete: "Done"
        }
    }

    // MARK: Story prompts

    /// Questions that use what was chosen, then the app's own, without repeats.
    static func questions(place: String?, songTitle: String?, date: Date?, hasMedia: Bool, insightQuestion: String?) -> [String] {
        var questions: [String] = []
        if let place, !place.isEmpty { questions.append("What were you doing in \(place)?") }
        if let songTitle { questions.append("Where were you when “\(songTitle)” found you?") }
        if let date { questions.append("What do you remember about \(date.formatted(.dateTime.month(.wide).year()))?") }
        if hasMedia { questions.append("Who was there with you?") }
        if let insightQuestion, !insightQuestion.isEmpty { questions.append(insightQuestion) }
        questions.append("What comes back to you?")
        var seen = Set<String>()
        return questions.filter { seen.insert($0).inserted }
    }

    static func question(at index: Int, in questions: [String]) -> String {
        questions.isEmpty ? "What comes back to you?" : questions[((index % questions.count) + questions.count) % questions.count]
    }

    // MARK: Date from a photo

    /// The capture date in a photo's EXIF data, so a picked photo dates the memory.
    static func captureDate(fromImageData data: Data) -> Date? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let exif = properties[kCGImagePropertyExifDictionary] as? [CFString: Any],
              let text = exif[kCGImagePropertyExifDateTimeOriginal] as? String else { return nil }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy:MM:dd HH:mm:ss"
        return formatter.date(from: text)
    }
}
