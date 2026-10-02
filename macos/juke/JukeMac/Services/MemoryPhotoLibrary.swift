import SwiftUI
import Photos
import Observation

@MainActor @Observable
final class MemoryPhotoLibrary {
    var assets: [PHAsset] = []
    var status = PHPhotoLibrary.authorizationStatus(for: .readWrite)
    var isLoading = false
    var canLoadMore = false
    var year: Int?
    private var limit = 60

    func chooseYear(_ value: Int?) async { year = value; limit = 60; await open() }

    func open(requestPermission: Bool = false) async {
        isLoading = true
        defer { isLoading = false }
        status = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        if requestPermission && status == .notDetermined { status = await PHPhotoLibrary.requestAuthorization(for: .readWrite) }
        guard status == .authorized || status == .limited else { assets = []; return }
        let options = PHFetchOptions()
        options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        options.predicate = NSPredicate(format: "mediaType == %d OR mediaType == %d", PHAssetMediaType.image.rawValue, PHAssetMediaType.video.rawValue)
        if let year, let from = Calendar.current.date(from: DateComponents(year: year, month: 1, day: 1)), let to = Calendar.current.date(byAdding: .year, value: 1, to: from) {
            options.predicate = NSCompoundPredicate(andPredicateWithSubpredicates: [options.predicate!, NSPredicate(format: "creationDate >= %@ AND creationDate < %@", from as NSDate, to as NSDate)])
        }
        options.fetchLimit = limit + 1
        let results = PHAsset.fetchAssets(with: options)
        canLoadMore = results.count > limit
        assets = (0..<min(limit, results.count)).map { results.object(at: $0) }
    }
    func more() async { limit += 60; await open() }

    /// Years that contain at least one photo or video, newest first; one limit-1 fetch per year keeps large libraries cheap.
    var years: [Int] = []
    func loadYears() async {
        guard status == .authorized || status == .limited, years.isEmpty else { return }
        years = await Task.detached(priority: .utility) {
            let media = NSPredicate(format: "mediaType == %d OR mediaType == %d", PHAssetMediaType.image.rawValue, PHAssetMediaType.video.rawValue)
            func edge(ascending: Bool) -> Date? {
                let options = PHFetchOptions()
                options.predicate = NSCompoundPredicate(andPredicateWithSubpredicates: [media, NSPredicate(format: "creationDate != nil")])
                options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: ascending)]
                options.fetchLimit = 1
                return PHAsset.fetchAssets(with: options).firstObject?.creationDate
            }
            let calendar = Calendar.current
            guard let oldest = edge(ascending: true), let newest = edge(ascending: false) else { return [] }
            return (calendar.component(.year, from: oldest)...calendar.component(.year, from: newest)).reversed().filter { year in
                guard let from = calendar.date(from: DateComponents(year: year, month: 1, day: 1)), let to = calendar.date(byAdding: .year, value: 1, to: from) else { return false }
                let options = PHFetchOptions()
                options.predicate = NSCompoundPredicate(andPredicateWithSubpredicates: [media, NSPredicate(format: "creationDate >= %@ AND creationDate < %@", from as NSDate, to as NSDate)])
                options.fetchLimit = 1
                return PHAsset.fetchAssets(with: options).count > 0
            }
        }.value
    }

    static func thumbnail(for asset: PHAsset, side: CGFloat = 600) async -> NSImage? {
        let bytes: Data? = await withCheckedContinuation { continuation in
            let options = PHImageRequestOptions(); options.deliveryMode = .highQualityFormat; options.isNetworkAccessAllowed = true
            PHImageManager.default().requestImage(for: asset, targetSize: CGSize(width: side, height: side), contentMode: .aspectFill, options: options) { image, _ in
                continuation.resume(returning: image?.tiffRepresentation)
            }
        }
        return bytes.flatMap(NSImage.init(data:))
    }

    static func file(for asset: PHAsset) async throws -> MemoryImportedFile {
        let resources = PHAssetResource.assetResources(for: asset)
        let preferred: PHAssetResourceType = asset.mediaType == .video ? .fullSizeVideo : .fullSizePhoto
        let fallback: PHAssetResourceType = asset.mediaType == .video ? .video : .photo
        guard let resource = resources.first(where: { $0.type == preferred }) ?? resources.first(where: { $0.type == fallback }) else {
            throw MemoryServiceError(message: "This photo isn’t available right now.")
        }
        let sink = PhotoDataDownload()
        let bytes = try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                sink.start(resource, continuation: continuation)
            }
        } onCancel: { sink.cancel() }
        try Task.checkCancellation()
        let directory = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString, directoryHint: .isDirectory)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: directory) }
        let url = directory.appendingPathComponent(URL(fileURLWithPath: resource.originalFilename).lastPathComponent)
        try bytes.write(to: url, options: .atomic)
        var file = try await MemoryImportedFile.read(url)
        file.metadata = MemoryCaptureMetadata(date: asset.creationDate, latitude: asset.location?.coordinate.latitude, longitude: asset.location?.coordinate.longitude).fillingMissing(from: file.metadata)
        return file
    }
}

// PhotoKit can deliver chunks on different queues. Bound memory and cancel oversized iCloud downloads.
private final class PhotoDataDownload: @unchecked Sendable {
    private let lock = NSLock()
    private var data = Data()
    private var continuation: CheckedContinuation<Data, Error>?
    private var request: PHAssetResourceDataRequestID?
    private var finished = false

    func start(_ resource: PHAssetResource, continuation: CheckedContinuation<Data, Error>) {
        let cancelled = lock.withLock { if finished { return true }; self.continuation = continuation; return false }
        if cancelled { continuation.resume(throwing: CancellationError()); return }
        let options = PHAssetResourceRequestOptions(); options.isNetworkAccessAllowed = true
        let id = PHAssetResourceManager.default().requestData(for: resource, options: options) { [self] chunk in
            let tooLarge = lock.withLock {
                guard !finished else { return false }
                guard data.count + chunk.count <= 50 * 1_024 * 1_024 else { return true }
                data.append(chunk); return false
            }
            if tooLarge { finish(error: MemoryServiceError(message: "This item is over 50 MB. Try a shorter video or another photo.")) }
        } completionHandler: { [self] error in finish(error: error) }
        let done = lock.withLock { request = id; return finished }
        if done { PHAssetResourceManager.default().cancelDataRequest(id) }
    }
    func cancel() { finish(error: CancellationError()) }
    private func finish(error: Error?) {
        let result: (CheckedContinuation<Data, Error>?, Data, PHAssetResourceDataRequestID?) = lock.withLock {
            guard !finished else { return (nil, Data(), nil) }
            finished = true
            let result = (continuation, data, request)
            continuation = nil; data = Data()
            return result
        }
        if let error { result.0?.resume(throwing: error); if let id = result.2 { PHAssetResourceManager.default().cancelDataRequest(id) } }
        else { result.0?.resume(returning: result.1) }
    }
}

struct MemoryPhotoTile: View {
    let asset: PHAsset
    let selected: Bool
    let toggle: () -> Void
    @State private var image: NSImage?
    @State private var request: PHImageRequestID?
    var body: some View {
        Button(action: toggle) {
            ZStack(alignment: .topTrailing) {
                Rectangle().fill(.white.opacity(0.08))
                if let image { Image(nsImage: image).resizable().scaledToFill() }
                else { Image(systemName: "photo").foregroundStyle(.secondary).frame(maxWidth: .infinity, maxHeight: .infinity) }
                Image(systemName: selected ? "checkmark.circle.fill" : "circle").font(.title2).foregroundStyle(selected ? Color.orange : .white).shadow(radius: 3).padding(9)
                if asset.mediaType == .video { Image(systemName: "play.fill").foregroundStyle(.white).padding(12).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading) }
            }.frame(height: 150).clipped().clipShape(RoundedRectangle(cornerRadius: 18))
                .overlay(RoundedRectangle(cornerRadius: 18).stroke(selected ? .orange : .clear, lineWidth: 3))
        }.buttonStyle(.plain)
            .accessibilityLabel("\(asset.mediaType == .video ? "Video" : "Photo"), \(asset.creationDate?.formatted(date: .abbreviated, time: .omitted) ?? "undated")")
            .accessibilityAddTraits(selected ? .isSelected : [])
            .onAppear {
                let options = PHImageRequestOptions(); options.deliveryMode = .opportunistic; options.isNetworkAccessAllowed = true
                request = PHImageManager.default().requestImage(for: asset, targetSize: CGSize(width: 350, height: 350), contentMode: .aspectFill, options: options) { result, _ in
                    let bytes = result?.tiffRepresentation
                    Task { @MainActor in if let bytes { image = NSImage(data: bytes) } }
                }
            }
            .onDisappear { if let request { PHImageManager.default().cancelImageRequest(request) } }
    }
}
