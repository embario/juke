import Foundation
import Testing
@testable import JukeApp

@Suite struct MemoryThumbnailTests {
    private func media(_ kind: String) -> MemoryMedia {
        MemoryMedia(id: UUID(), kind: kind, filename: "IMG_0001", contentType: kind == "video" ? "video/quicktime" : "image/jpeg", url: "/media/x")
    }

    private func memory(media: [MemoryMedia] = [], artwork: URL? = nil) -> MusicMemory {
        var song = MemorySong(title: "Song", artist: "Artist", provider: "spotify")
        song.artworkURL = artwork
        return MusicMemory(id: UUID(), title: "", text: "", occurredAt: Date(), createdAt: Date(), place: "", people: [],
                           songs: [song], media: media, tags: [], classification: .unavailable)
    }

    @Test func photoBeatsVideoAndArtwork() {
        let photo = media("image")
        let result = MemoryThumbnailChoice.choose(for: memory(media: [media("video"), photo], artwork: URL(string: "https://a.example/c.jpg")))
        #expect(result == .photo(photo))
    }

    @Test func videoBeatsArtwork() {
        let video = media("video")
        #expect(MemoryThumbnailChoice.choose(for: memory(media: [video], artwork: URL(string: "https://a.example/c.jpg"))) == .video(video))
    }

    @Test func songArtworkWhenNoMedia() {
        let url = URL(string: "https://a.example/c.jpg")!
        #expect(MemoryThumbnailChoice.choose(for: memory(artwork: url)) == .artwork(url))
    }

    @Test func placeholderWhenNothingToShow() {
        #expect(MemoryThumbnailChoice.choose(for: memory()) == .placeholder)
    }
}
