import XCTest
import ImageIO
import UniformTypeIdentifiers
@testable import Juke_Vibe

final class MemoryMediaImportTests: XCTestCase {
    func testImageMetadataReadsCaptureDateAndSignedGPSWithoutFilesystemDate() throws {
        let color = CGColorSpaceCreateDeviceRGB()
        let context = try XCTUnwrap(CGContext(data: nil, width: 2, height: 2, bitsPerComponent: 8, bytesPerRow: 8, space: color, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        let image = try XCTUnwrap(context.makeImage())
        let bytes = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(bytes, UTType.jpeg.identifier as CFString, 1, nil))
        let properties: [CFString: Any] = [
            kCGImagePropertyExifDictionary: [kCGImagePropertyExifDateTimeOriginal: "2021:07:04 18:30:00", kCGImagePropertyExifOffsetTimeOriginal: "+02:00"],
            kCGImagePropertyGPSDictionary: [kCGImagePropertyGPSLatitude: 33.9, kCGImagePropertyGPSLatitudeRef: "S", kCGImagePropertyGPSLongitude: 18.4, kCGImagePropertyGPSLongitudeRef: "E"]
        ]
        CGImageDestinationAddImage(destination, image, properties as CFDictionary)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        let metadata = MemoryCaptureMetadata.image(bytes as Data)
        XCTAssertEqual(metadata.date, ISO8601DateFormatter().date(from: "2021-07-04T16:30:00Z"))
        XCTAssertEqual(try XCTUnwrap(metadata.latitude), -33.9, accuracy: 0.001)
        XCTAssertEqual(try XCTUnwrap(metadata.longitude), 18.4, accuracy: 0.001)
        XCTAssertTrue(metadata.hasLocation)
    }

    func testMissingOrInvalidMetadataStaysUnknown() {
        XCTAssertEqual(MemoryCaptureMetadata.image(Data()), MemoryCaptureMetadata())
        XCTAssertNil(MemoryCaptureMetadata.parseEXIFDate("not a date", offset: nil))
        XCTAssertFalse(MemoryCaptureMetadata(latitude: 91, longitude: 0).hasLocation)
        XCTAssertFalse(MemoryCaptureMetadata(latitude: 0, longitude: .nan).hasLocation)
        XCTAssertTrue(MemoryCaptureMetadata(latitude: 0, longitude: 0).hasLocation)
    }

    func testPhotoDateUsesFirstKnownCaptureAndManualOverrideSurvivesImports() {
        let now = Date(timeIntervalSince1970: 9000)
        let first = Date(timeIntervalSince1970: 1000)
        let second = Date(timeIntervalSince1970: 2000)
        var choice = MemoryMomentSelection(startedAt: now)
        let metadata = [MemoryCaptureMetadata(), MemoryCaptureMetadata(date: first), MemoryCaptureMetadata(date: second)]
        XCTAssertEqual(choice.date(from: metadata), first)
        XCTAssertTrue(choice.isPhotoDate(metadata))
        choice.manualDate = now
        XCTAssertEqual(choice.date(from: metadata), now)
        XCTAssertFalse(choice.isPhotoDate(metadata))
        choice.manualDate = nil
        XCTAssertEqual(choice.date(from: [MemoryCaptureMetadata(date: second)]), second)
        XCTAssertEqual(choice.date(from: []), now)
        XCTAssertFalse(choice.isPhotoDate([]))
    }

    func testCustomStoryTagsHandleUnicodeDeduplicationAndPunctuation() {
        XCTAssertEqual(MemoryDraft.storyTags("We sang #Road-trip, #été, #road-trip! A#not-a-tag and #東京"), ["Road-trip", "été", "東京"])
    }

    func testOversizedFileRejectedBeforeImport() async throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString).appendingPathExtension("mov")
        FileManager.default.createFile(atPath: url.path, contents: nil)
        defer { try? FileManager.default.removeItem(at: url) }
        let handle = try FileHandle(forWritingTo: url)
        try handle.truncate(atOffset: 51 * 1024 * 1024)
        try handle.close()
        do { _ = try await MemoryImportedFile.read(url); XCTFail("Oversized media must not be loaded") }
        catch { XCTAssertTrue(error.localizedDescription.contains("50 MB")) }
    }
    func testLibraryEnrichmentPreservesEmbeddedMetadataWhenLibraryFieldsAreMissing() {
        let embedded = MemoryCaptureMetadata(date: Date(timeIntervalSince1970: 1000), latitude: 10, longitude: 20)
        XCTAssertEqual(MemoryCaptureMetadata().fillingMissing(from: embedded), embedded)
        let adjustedDate = Date(timeIntervalSince1970: 2000)
        let library = MemoryCaptureMetadata(date: adjustedDate)
        let merged = library.fillingMissing(from: embedded)
        XCTAssertEqual(merged.date, adjustedDate)
        XCTAssertEqual(merged.latitude, 10)
    }

    func testFixtureMediaRoundTripNeverNeedsLiveBackend() async throws {
        let client = MemoryClient(fixtures: true)
        let bytes = Data("synthetic preview bytes".utf8)
        let media = try await client.upload(data: bytes, filename: "fixture.jpg", contentType: "image/jpeg", token: "fixture-token")
        var draft = MemoryDraft(); draft.mediaIDs = [media.id]
        let memory = try await client.create(draft, token: "fixture-token")
        XCTAssertEqual(memory.title, "")
        XCTAssertEqual(memory.media, [media])
        let result = try await client.mediaData(media, token: "fixture-token")
        XCTAssertEqual(result, bytes)
    }

}
