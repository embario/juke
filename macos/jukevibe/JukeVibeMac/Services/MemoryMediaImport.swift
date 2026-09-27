import Foundation
import Photos
import CoreLocation
import MapKit
import CoreTransferable
import ImageIO
import AVFoundation
import UniformTypeIdentifiers

struct MemoryCaptureMetadata: Equatable, Sendable {
    var date: Date?
    var latitude: Double?
    var longitude: Double?

    static func image(_ data: Data) -> Self {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [String: Any] else { return Self() }
        let exif = props[kCGImagePropertyExifDictionary as String] as? [String: Any] ?? [:]
        let gps = props[kCGImagePropertyGPSDictionary as String] as? [String: Any] ?? [:]
        var result = Self(date: parseEXIFDate(exif[kCGImagePropertyExifDateTimeOriginal as String] as? String,
                                             offset: exif[kCGImagePropertyExifOffsetTimeOriginal as String] as? String))
        if let lat = gps[kCGImagePropertyGPSLatitude as String] as? Double,
           let lon = gps[kCGImagePropertyGPSLongitude as String] as? Double {
            result.latitude = lat * ((gps[kCGImagePropertyGPSLatitudeRef as String] as? String) == "S" ? -1 : 1)
            result.longitude = lon * ((gps[kCGImagePropertyGPSLongitudeRef as String] as? String) == "W" ? -1 : 1)
            if !result.hasLocation { result.latitude = nil; result.longitude = nil }
        }
        return result
    }

    func fillingMissing(from fallback: Self) -> Self {
        Self(date: date ?? fallback.date,
             latitude: hasLocation ? latitude : fallback.latitude,
             longitude: hasLocation ? longitude : fallback.longitude)
    }

    var hasLocation: Bool {
        guard let latitude, let longitude else { return false }
        return latitude.isFinite && longitude.isFinite && (-90...90).contains(latitude) && (-180...180).contains(longitude)
    }

    static func parseEXIFDate(_ raw: String?, offset: String?) -> Date? {
        guard let raw else { return nil }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.isLenient = false
        formatter.dateFormat = offset == nil ? "yyyy:MM:dd HH:mm:ss" : "yyyy:MM:dd HH:mm:ssXXXXX"
        return formatter.date(from: raw + (offset ?? ""))
    }

    // Public PhotoKit exposes capture metadata, but not the Photos People identities.
    static func authorizedAsset(_ id: String?) -> Self? {
        let status = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        guard status == .authorized || status == .limited, let id,
              let asset = PHAsset.fetchAssets(withLocalIdentifiers: [id], options: nil).firstObject else { return nil }
        return Self(date: asset.creationDate, latitude: asset.location?.coordinate.latitude, longitude: asset.location?.coordinate.longitude)
    }

    func placeName() async -> String? {
        guard hasLocation, let latitude, let longitude else { return nil }
        guard let request = MKReverseGeocodingRequest(location: CLLocation(latitude: latitude, longitude: longitude)),
              let place = try? await request.mapItems.first else { return nil }
        return place.addressRepresentations?.cityWithContext ?? place.addressRepresentations?.regionName
    }
}

struct MemoryImportedFile: Transferable, Sendable {
    let data: Data
    let filename: String
    let contentType: String
    var metadata: MemoryCaptureMetadata
    let thumbnail: Data?

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(importedContentType: .image) { try await read($0.file) }
        FileRepresentation(importedContentType: .movie) { try await read($0.file) }
    }

    static func read(_ url: URL) async throws -> Self {
        let values = try url.resourceValues(forKeys: [.fileSizeKey, .contentTypeKey])
        guard let size = values.fileSize, size > 0, size <= 50 * 1_024 * 1_024 else {
            throw MemoryServiceError(message: "Choose a photo or video smaller than 50 MB.")
        }
        let data = try Data(contentsOf: url)
        let type = values.contentType ?? UTType(filenameExtension: url.pathExtension) ?? .data
        var metadata = MemoryCaptureMetadata.image(data)
        var preview: CGImage?
        if type.conforms(to: .movie) {
            let asset = AVURLAsset(url: url)
            if let item = try? await asset.load(.creationDate) { metadata.date = try? await item.load(.dateValue) }
            let items = (try? await asset.load(.metadata)) ?? []
            let locations = AVMetadataItem.metadataItems(from: items, filteredByIdentifier: .quickTimeMetadataLocationISO6709)
            if let item = locations.first, let raw = try? await item.load(.stringValue),
               let match = raw.range(of: "^[+-][0-9]+(?:\\.[0-9]+)?[+-][0-9]+(?:\\.[0-9]+)?", options: .regularExpression) {
                let coordinates = String(raw[match])
                if let split = coordinates.dropFirst().firstIndex(where: { $0 == "+" || $0 == "-" }) {
                    metadata.latitude = Double(coordinates[..<split]); metadata.longitude = Double(coordinates[split...])
                }
            }
            let generator = AVAssetImageGenerator(asset: asset)
            generator.appliesPreferredTrackTransform = true
            generator.maximumSize = CGSize(width: 600, height: 600)
            preview = try? await generator.image(at: .zero).image
        } else if let source = CGImageSourceCreateWithData(data as CFData, nil) {
            preview = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 600, kCGImageSourceCreateThumbnailWithTransform: true] as CFDictionary)
        }
        var thumbnail: Data?
        if let preview {
            let output = NSMutableData()
            if let destination = CGImageDestinationCreateWithData(output, UTType.jpeg.identifier as CFString, 1, nil) {
                CGImageDestinationAddImage(destination, preview, nil)
                if CGImageDestinationFinalize(destination) { thumbnail = output as Data }
            }
        }
        return Self(data: data, filename: url.lastPathComponent, contentType: type.preferredMIMEType ?? "application/octet-stream", metadata: metadata, thumbnail: thumbnail)
    }
}

struct MemoryMomentSelection: Equatable {
    var manualDate: Date?
    var usePhotoPlace = true
    let startedAt: Date

    init(startedAt: Date = Date()) { self.startedAt = startedAt }
    func date(from metadata: [MemoryCaptureMetadata]) -> Date { manualDate ?? metadata.compactMap(\.date).first ?? startedAt }
    func isPhotoDate(_ metadata: [MemoryCaptureMetadata]) -> Bool { manualDate == nil && metadata.contains { $0.date != nil } }
}
