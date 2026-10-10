import AVKit
import PhotosUI
import SwiftUI
import UIKit

/// One memory, opened from the deck: its picture, description, song (with a ringed Play), photos and videos, and tags.
/// The description, attachments and tags can all be added to after the fact.
struct MemoryDetail: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.colorScheme) private var scheme
    @Environment(\.dynamicTypeSize) private var typeSize
    let memory: MusicMemory
    @State private var newTag = ""
    @State private var error: String?
    @State private var editingDescription = false
    @State private var draftDescription = ""
    @State private var savingDescription = false
    @State private var picks: [PhotosPickerItem] = []
    @State private var uploading = false
    @State private var mediaToRemove: MemoryMedia?
    @State private var imageViewerItem: MemoryImageViewerItem?

    private var current: MusicMemory { model.memories.memories.first { $0.id == memory.id } ?? memory }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header
                ForEach(current.songs) { songCapsule($0) }
                if let message = model.memoryPlayer.message { Text(message).font(.footnote).foregroundStyle(.secondary) }
                descriptionSection
                mediaSection
                tagsSection
                if !current.people.isEmpty { peopleSection }
                if let error { Text(error).font(.footnote).foregroundStyle(.red).accessibilityIdentifier("memory.error") }
            }
            .padding(20)
            .padding(.bottom, 110)  // clear of the player island and tab bar
        }
        .background(VibeBackground(atmosphere: model.atmosphere))
        .navigationTitle(current.displayTitle).navigationBarTitleDisplayMode(.inline)
        .scrollDismissesKeyboard(.interactively)
        .toolbar {
            // In the bar, not under the text: the keyboard would cover a button below the field.
            if editingDescription {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { Task { await saveDescription() } } label: { if savingDescription { ProgressView() } else { Text("Save").bold() } }
                        .disabled(savingDescription || MemoryDetailLogic.descriptionChange(from: current.text, to: draftDescription) == nil)
                        .accessibilityIdentifier("memory.description.save")
                }
            }
        }
        .onChange(of: picks) { _, items in Task { await upload(items) } }
        .confirmationDialog("Remove this attachment?", isPresented: Binding(get: { mediaToRemove != nil }, set: { if !$0 { mediaToRemove = nil } }), titleVisibility: .visible) {
            Button("Remove", role: .destructive) { if let media = mediaToRemove { Task { await remove(media) } } }
            Button("Cancel", role: .cancel) { mediaToRemove = nil }
        } message: { Text("It is deleted from this memory.") }
        .fullScreenCover(item: $imageViewerItem) { MemoryFullscreenViewer(item: $0) }
    }

    // MARK: Sections

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            GeometryReader { proxy in
                // A wide crop of the picture, so the description is in view without scrolling.
                if let item = MemoryThumbnailChoice.choose(for: current).viewerItem {
                    Button { imageViewerItem = item } label: {
                        MemoryThumbnail(memory: current, side: proxy.size.width, cornerRadius: 0)
                            .frame(width: proxy.size.width, height: proxy.size.width)
                            .frame(height: proxy.size.width * 0.62)
                            .clipped()
                            .clipShape(RoundedRectangle(cornerRadius: 14))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(item.isVideo ? "View memory video" : "View memory image")
                    .accessibilityIdentifier("memory.detail.image")
                } else {
                    MemoryThumbnail(memory: current, side: proxy.size.width, cornerRadius: 0)
                        .frame(width: proxy.size.width, height: proxy.size.width)
                        .frame(height: proxy.size.width * 0.62)
                        .clipped()
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                }
            }
            .aspectRatio(1 / 0.62, contentMode: .fit)
            .shadow(color: .black.opacity(0.2), radius: 12, y: 6)
            Text(current.displayTitle).font(.system(.title, design: .rounded, weight: .bold))
            Text(MemoryDetailLogic.context(current)).font(.subheadline).foregroundStyle(.secondary)
        }
    }

    private func songCapsule(_ song: MemorySong) -> some View {
        HStack(spacing: 12) {
            if let artwork = song.artworkURL {
                Button { imageViewerItem = .artwork(artwork) } label: {
                    AsyncImage(url: artwork) { $0.resizable().scaledToFill() } placeholder: {
                        ZStack { Color.secondary.opacity(0.15); Image(systemName: "music.note").foregroundStyle(.secondary) }
                    }
                    .frame(width: 52, height: 52).clipShape(RoundedRectangle(cornerRadius: 10))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("View song artwork")
                .accessibilityIdentifier("memory.song.artwork")
            } else {
                ZStack { Color.secondary.opacity(0.15); Image(systemName: "music.note").foregroundStyle(.secondary) }
                    .frame(width: 52, height: 52).clipShape(RoundedRectangle(cornerRadius: 10))
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(song.title).font(.headline).lineLimit(typeSize.isAccessibilitySize ? nil : 2)
                Text(song.artist).font(.subheadline).foregroundStyle(.secondary).lineLimit(typeSize.isAccessibilitySize ? nil : 1)
                if let segment = song.segmentDescription { Text("The moment \(segment)").font(.caption).foregroundStyle(.tertiary) }
            }
            Spacer(minLength: 8)
            RingedPlayButton(label: song.segmentDescription == nil ? "Play \(song.title)" : "Play the moment", disabled: model.memoryPlayer.isBusy) {
                Task { await model.memoryPlayer.play(song, in: current.id) }
            }
        }
        .padding(12)
        .background(MemoryDetailStyle.well(scheme), in: RoundedRectangle(cornerRadius: 34, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("memory.songCapsule")
    }

    private var descriptionSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Description").font(.headline)
                Spacer()
                if !editingDescription {
                    Button(current.text.isEmpty ? "Add" : "Edit") { draftDescription = current.text; editingDescription = true }
                        .accessibilityIdentifier("memory.description.edit")
                }
            }
            if editingDescription {
                TextEditor(text: $draftDescription)
                    .frame(minHeight: 120).padding(8)
                    .background(MemoryDetailStyle.well(scheme), in: RoundedRectangle(cornerRadius: 12))
                    .accessibilityIdentifier("memory.description.field")
                Button("Cancel", role: .cancel) { editingDescription = false }.accessibilityIdentifier("memory.description.cancel")
            } else if current.text.isEmpty {
                Text("What was happening? Add a few words to keep the moment.").foregroundStyle(.secondary)
            } else {
                Text(current.text).accessibilityIdentifier("memory.description")
            }
        }
    }

    private var mediaSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Photos and videos").font(.headline)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(current.media) { media in
                        MemoryMediaTile(media: media) { imageViewerItem = .attachment(media) }
                            .contextMenu {
                                if MemoryDetailLogic.canRemove(media, from: current) {
                                    Button("Remove", systemImage: "trash", role: .destructive) { mediaToRemove = media }
                                }
                            }
                    }
                    PhotosPicker(selection: $picks, maxSelectionCount: 8, matching: .any(of: [.images, .videos])) {
                        VStack(spacing: 6) {
                            if uploading { ProgressView() } else { Image(systemName: "photo.badge.plus").font(.title) }
                            Text("Add").font(.footnote)
                        }
                        .frame(width: 120, height: 160)
                        .background(MemoryDetailStyle.well(scheme), in: RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(.secondary.opacity(0.4), style: StrokeStyle(lineWidth: 1, dash: [5, 4])))
                    }
                    .disabled(uploading)
                    .accessibilityLabel("Add photos or videos").accessibilityIdentifier("memory.media.add")
                }
            }
            Text(MemoryDetailLogic.mediaSummary(current)).font(.footnote).foregroundStyle(.secondary).accessibilityIdentifier("memory.media.summary")
        }
    }

    private var tagsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Tags").font(.headline)
            FlowLayout(spacing: 8) {
                ForEach(current.tags, id: \.self) { tag in
                    HStack(spacing: 4) {
                        Text("#\(tag)")
                        Button { Task { await setTags(current.tags.filter { $0 != tag }) } } label: { Image(systemName: "xmark.circle.fill") }
                            .buttonStyle(.plain).accessibilityLabel("Remove \(tag)")
                    }
                    .font(.subheadline).padding(.horizontal, 12).padding(.vertical, 7)
                    .background(model.atmosphere.primary.opacity(0.18), in: Capsule())
                }
            }
            .accessibilityIdentifier("memory.tags")
            HStack {
                TextField("Add a tag", text: $newTag).onSubmit(addTag).textInputAutocapitalization(.never)
                    .accessibilityIdentifier("memory.tag.field")
                Button("Add", action: addTag).disabled(newTag.trimmingCharacters(in: .whitespaces).isEmpty)
                    .accessibilityIdentifier("memory.tag.add")
            }
            .padding(10).background(MemoryDetailStyle.well(scheme), in: RoundedRectangle(cornerRadius: 12))
            let suggestions = MemoryDetailLogic.suggestedTags(for: current, vocabulary: model.memories.reusableTags)
            if !suggestions.isEmpty {
                Text("Suggested").font(.footnote).foregroundStyle(.secondary)
                FlowLayout(spacing: 8) {
                    ForEach(suggestions, id: \.self) { tag in
                        Button { Task { await setTags(current.tags + [tag]) } } label: {
                            Label(tag, systemImage: "plus").font(.subheadline)
                                .padding(.horizontal, 12).padding(.vertical, 7)
                                .overlay(Capsule().strokeBorder(.secondary.opacity(0.5)))
                        }
                        .buttonStyle(.plain).accessibilityLabel("Add tag \(tag)")
                    }
                }
                .accessibilityIdentifier("memory.tags.suggested")
            }
        }
    }

    private var peopleSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("With").font(.headline)
            FlowLayout(spacing: 8) {
                ForEach(current.people, id: \.self) { person in
                    Label(person, systemImage: "person.fill").font(.subheadline)
                        .padding(.horizontal, 12).padding(.vertical, 7)
                        .background(MemoryDetailStyle.well(scheme), in: Capsule())
                }
            }
        }
    }

    // MARK: Actions

    private func addTag() {
        let tag = newTag; newTag = ""
        Task { await setTags(current.tags + [tag]) }
    }

    private func setTags(_ tags: [String]) async {
        do { try await model.memories.updateTags(tags, for: current); error = nil }
        catch { self.error = error.localizedDescription }
    }

    private func saveDescription() async {
        guard let text = MemoryDetailLogic.descriptionChange(from: current.text, to: draftDescription) else { editingDescription = false; return }
        savingDescription = true
        defer { savingDescription = false }
        do { try await model.memories.updateDescription(text, for: current); editingDescription = false; error = nil }
        catch { self.error = (error as? LocalizedError)?.errorDescription ?? "The description couldn’t be saved." }
    }

    private func upload(_ items: [PhotosPickerItem]) async {
        guard !items.isEmpty else { return }
        uploading = true; error = nil
        defer { uploading = false; picks = [] }
        var added: [MemoryMedia] = []
        for item in items {
            do {
                guard let data = try await item.loadTransferable(type: Data.self) else { continue }
                let type = item.supportedContentTypes.first
                let ext = type?.preferredFilenameExtension ?? "jpg"
                added.append(try await model.memories.upload(data, filename: "memory-\(UUID().uuidString.prefix(8)).\(ext)", contentType: type?.preferredMIMEType ?? "image/jpeg"))
            } catch { self.error = (error as? LocalizedError)?.errorDescription ?? "That attachment could not be added." }
        }
        guard !added.isEmpty else { return }
        do { try await model.memories.attach(added, to: current) }
        catch {
            await model.memories.discardMedia(added)
            self.error = (error as? LocalizedError)?.errorDescription ?? "The attachments couldn’t be saved."
        }
    }

    private func remove(_ media: MemoryMedia) async {
        mediaToRemove = nil
        do { try await model.memories.detach(media, from: current); error = nil }
        catch { self.error = (error as? LocalizedError)?.errorDescription ?? "The attachment couldn’t be removed." }
    }
}

/// A round Play button with a visible ring around it, made to sit at the trailing edge of a capsule.
struct RingedPlayButton: View {
    @Environment(VibeAppModel.self) private var model
    let label: String
    var disabled = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: "play.fill").font(.system(size: 18, weight: .bold)).foregroundStyle(.white)
                .frame(width: 44, height: 44)
                .background(model.atmosphere.primary, in: Circle())
                .padding(3)
                .overlay(Circle().strokeBorder(model.atmosphere.primary, lineWidth: 2))
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .disabled(disabled)
        .opacity(disabled ? 0.5 : 1)
        .accessibilityLabel(label).accessibilityIdentifier("memory.playMoment")
    }
}

/// A photo or video attachment, large enough to look at, with a play badge on videos.
private struct MemoryMediaTile: View {
    @Environment(VibeAppModel.self) private var model
    let media: MemoryMedia
    let open: () -> Void
    @State private var image: UIImage?
    @State private var failed = false

    var body: some View {
        Button(action: open) {
            ZStack {
                Color.secondary.opacity(0.15)
                if let image { Image(uiImage: image).resizable().scaledToFill() }
                else if failed { Image(systemName: media.kind == "video" ? "play.rectangle" : "photo").foregroundStyle(.secondary) }
                else { ProgressView() }
                if media.kind == "video", image != nil {
                    Image(systemName: "play.circle.fill").font(.system(size: 40)).foregroundStyle(.white).shadow(radius: 4)
                }
            }
            .frame(width: 160, height: 200).clipShape(RoundedRectangle(cornerRadius: 12))
            .task {
                do {
                    let url = try await model.memories.localMediaURL(media)
                    image = media.kind == "video" ? await MemoryImageDecoder.videoFrame(url, maxPixel: 640) : MemoryImageDecoder.downsampled(url, maxPixel: 960)
                    if image == nil { failed = true }
                } catch { failed = true }
            }
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(media.kind == "video" ? "Video attachment" : "Photo attachment")
        .accessibilityIdentifier(media.kind == "video" ? "memory.video" : "memory.photo")
    }
}

enum MemoryDetailStyle {
    static func well(_ scheme: ColorScheme) -> Color { scheme == .dark ? Color(white: 0.17) : Color(white: 0.96) }
}

/// Wraps its children onto as many lines as they need.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrange(width: proposal.width ?? .infinity, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = arrange(width: bounds.width, subviews: subviews)
        for (subview, origin) in zip(subviews, result.origins) {
            subview.place(at: CGPoint(x: bounds.minX + origin.x, y: bounds.minY + origin.y), proposal: .unspecified)
        }
    }

    private func arrange(width: CGFloat, subviews: Subviews) -> (size: CGSize, origins: [CGPoint]) {
        var origins: [CGPoint] = []
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0, maxX: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0, x + size.width > width { x = 0; y += rowHeight + spacing; rowHeight = 0 }
            origins.append(CGPoint(x: x, y: y))
            x += size.width + spacing; rowHeight = max(rowHeight, size.height); maxX = max(maxX, x - spacing)
        }
        return (CGSize(width: maxX, height: y + rowHeight), origins)
    }
}
