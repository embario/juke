import Foundation
import Testing
@testable import JukeApp

@Suite struct MemoryDetailLogicTests {
    private func media(_ kind: String) -> MemoryMedia {
        MemoryMedia(id: UUID(), kind: kind, filename: "f", contentType: kind == "video" ? "video/quicktime" : "image/jpeg", url: "")
    }

    private func memory(text: String = "", songs: [MemorySong] = [], media: [MemoryMedia] = [], tags: [String] = [], generated: [String] = [], place: String = "") -> MusicMemory {
        var memory = MusicMemory(id: UUID(), title: "T", text: text, occurredAt: Date(timeIntervalSince1970: 1_700_000_000), createdAt: Date(),
                                 place: place, people: [], songs: songs, media: media, tags: tags, classification: .unavailable)
        memory.generatedTags = generated
        return memory
    }

    private let song = MemorySong(title: "So What", artist: "Miles Davis", provider: "spotify", providerID: "x")

    @Test func aDescriptionChangeIgnoresSurroundingWhitespace() {
        #expect(MemoryDetailLogic.descriptionChange(from: "Hello", to: "  Hello \n") == nil)
        #expect(MemoryDetailLogic.descriptionChange(from: "Hello", to: "Hello there ") == "Hello there")
        #expect(MemoryDetailLogic.descriptionChange(from: "Hello", to: "  ") == "", "clearing the description is a change")
        #expect(MemoryDetailLogic.descriptionChange(from: "", to: "\n") == nil, "blank to blank is nothing")
    }

    @Test func suggestionsAreClassifierTagsThenVocabularyWithoutRepeatsOrWhatTheMemoryHas() {
        let m = memory(tags: ["Summer"], generated: ["beach", "summer", "road trip"])
        let suggestions = MemoryDetailLogic.suggestedTags(for: m, vocabulary: ["Road Trip", "family", "SUMMER", " "])
        #expect(suggestions == ["beach", "road trip", "family"])
    }

    @Test func suggestionsAreCapped() {
        let vocabulary = (1...30).map { "tag\($0)" }
        #expect(MemoryDetailLogic.suggestedTags(for: memory(), vocabulary: vocabulary, limit: 5) == ["tag1", "tag2", "tag3", "tag4", "tag5"])
        #expect(MemoryDetailLogic.suggestedTags(for: memory(), vocabulary: vocabulary).count == 12)
        #expect(MemoryDetailLogic.suggestedTags(for: memory(), vocabulary: []).isEmpty)
    }

    @Test func attachmentsSplitIntoPhotosAndVideosInOrder() {
        let a = media("image"), b = media("video"), c = media("photo"), d = media("video")
        let m = memory(media: [a, b, c, d])
        #expect(MemoryDetailLogic.photos(m).map(\.id) == [a.id, c.id], "anything that is not a video is a photo")
        #expect(MemoryDetailLogic.videos(m).map(\.id) == [b.id, d.id])
    }

    @Test func theLastThingCannotBeRemovedFromAMemory() {
        let only = media("image")
        #expect(!MemoryDetailLogic.canRemove(only, from: memory(media: [only])), "the server rejects an empty memory")
        #expect(MemoryDetailLogic.canRemove(only, from: memory(media: [only], tags: ["x"])) == false, "tags alone do not keep a memory")
        #expect(MemoryDetailLogic.canRemove(only, from: memory(text: "Words", media: [only])))
        #expect(MemoryDetailLogic.canRemove(only, from: memory(songs: [song], media: [only])))
        #expect(MemoryDetailLogic.canRemove(only, from: memory(media: [only, media("video")])))
    }

    @Test func contextLineJoinsDateAndPlace() {
        #expect(!MemoryDetailLogic.context(memory()).contains("·"))
        #expect(MemoryDetailLogic.context(memory(place: "Brooklyn")).hasSuffix("· Brooklyn"))
    }

    @Test func mediaSummaryCountsEachKind() {
        #expect(MemoryDetailLogic.mediaSummary(memory()) == "No photos or videos yet")
        #expect(MemoryDetailLogic.mediaSummary(memory(media: [media("image")])) == "1 photo")
        #expect(MemoryDetailLogic.mediaSummary(memory(media: [media("image"), media("image"), media("video")])) == "2 photos · 1 video")
        #expect(MemoryDetailLogic.mediaSummary(memory(media: [media("video"), media("video")])) == "2 videos")
    }
}
