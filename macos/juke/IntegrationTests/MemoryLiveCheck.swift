import Foundation
import AppKit
import AVFoundation

@main struct LiveCheck {
    static func main() async throws {
        let credentials = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: ProcessInfo.processInfo.environment["VIBE_TEST_CREDENTIALS"] ?? "/tmp/juke-vibe-test-credentials.json"))) as! [String: String]
        let session = URLSession(configuration: .ephemeral)
        defer { session.invalidateAndCancel() }
        let root = URL(string: credentials["baseURL"]!)!
        var login = URLRequest(url: root.appending(path: "api/v1/auth/accounts/login/"))
        login.httpMethod = "POST"; login.setValue("application/json", forHTTPHeaderField: "Content-Type")
        login.httpBody = try JSONSerialization.data(withJSONObject: ["login": credentials["username"]!, "password": credentials["password"]!])
        let (loginData, loginResponse) = try await session.data(for: login)
        precondition((loginResponse as! HTTPURLResponse).statusCode == 200, "Login failed")
        let loginJSON = try JSONSerialization.jsonObject(with: loginData) as! [String: Any]
        let token = loginJSON["token"] as! String
        let base = root.appending(path: "api/v1/vibe/")
        let client = MemoryClient(baseURL: base)
        let photoData = try Data(contentsOf: URL(fileURLWithPath: "/tmp/vibe-memory-fixture.png"))
        let videoData = try Data(contentsOf: URL(fileURLWithPath: "/tmp/vibe-memory-fixture.mp4"))
        let photo = try await client.upload(data: photoData, filename: "moment.png", contentType: "image/png", token: token)
        let video = try await client.upload(data: videoData, filename: "moment.mp4", contentType: "video/mp4", token: token)
        precondition(photo.kind == "photo" && video.kind == "video")
        var draft = MemoryDraft()
        draft.title = "Live multimedia journey"; draft.text = "Remembering a test sunset with friends."
        draft.place = "Test beach"; draft.people = ["Test friend"]; draft.tags = ["Live test tag"]
        var song = MemorySong(title: "Blue in Green", artist: "Miles Davis", provider: "spotify", providerID: "0aWMVrwxPNYkKmFthzmpRi", playbackURL: URL(string: "https://open.spotify.com/track/0aWMVrwxPNYkKmFthzmpRi"))
        song.startSeconds = 12; song.endSeconds = 24
        draft.songs = [song, MemorySong(title: "A second song", artist: "Test artist", provider: "appleMusic")]
        draft.mediaIDs = [photo.id, video.id]
        let classification = try await client.classify(draft, token: token)
        precondition(classification.status == "unavailable" && classification.tags.isEmpty)
        let saved = try await client.create(draft, token: token)
        precondition(saved.media.count == 2 && saved.songs.count == 2 && saved.songs[0].startSeconds == 12)
        precondition(saved.songs[1].playbackURL == nil)
        let listed = try await client.list(token: token)
        precondition(listed.contains { $0.id == saved.id })
        let loadedPhoto = try await client.mediaData(photo, token: token)
        precondition(loadedPhoto == photoData && NSImage(data: loadedPhoto) != nil)
        let loadedVideo = try await client.mediaData(video, token: token)
        precondition(loadedVideo == videoData)
        let videoURL = URL(fileURLWithPath: "/tmp/vibe-memory-downloaded.mp4")
        try loadedVideo.write(to: videoURL)
        let duration = try await AVURLAsset(url: videoURL).load(.duration)
        precondition(duration.seconds > 0)
        let updated = try await client.updateTags(memory: saved, tags: ["Reusable live tag"], token: token)
        precondition(updated.tags == ["Reusable live tag"])
        let tags = try await client.tags(token: token)
        precondition(tags.contains("Reusable live tag"))
        let insights = try await client.insights(token: token)
        precondition(insights.connections.contains { $0.label == "Test beach" && $0.memoryIDs.contains(saved.id) })
        var delete = URLRequest(url: base.appending(path: "memories/\(saved.id.uuidString.lowercased())/")); delete.httpMethod = "DELETE"
        delete.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        let (_, deletion) = try await session.data(for: delete)
        precondition((deletion as! HTTPURLResponse).statusCode == 204)
        print("PASS: real login → Jev boundary → photo/video upload → multi-song segment memory → browse → authenticated image/video decode → tag edit/reuse → profile connections → cleanup")
    }
}
