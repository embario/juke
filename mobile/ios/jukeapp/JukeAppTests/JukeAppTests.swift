import Foundation
import Testing
@testable import JukeApp

struct JukeAppTests {
    @Test func catalogSubtitlePrefersArtist() throws {
        let data = #"{"pk":1,"name":"Song","artist_names":"Artist","album_name":"Album","spotify_data":null}"#.data(using: .utf8)!
        let item = try JSONDecoder().decode(CatalogItem.self, from: data)
        #expect(item.subtitle == "Artist")
    }
}
