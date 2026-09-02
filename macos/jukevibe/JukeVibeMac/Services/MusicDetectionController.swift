import Foundation
import Observation

@MainActor
@Observable
final class MusicDetectionController {
    enum Mode: String, CaseIterable, Identifiable {
        case playerMetadata, microphone, systemAudio
        var id: String { rawValue }
        var title: String {
            switch self {
            case .playerMetadata: "Spotify & Apple Music"
            case .microphone: "Around Me"
            case .systemAudio: "This Mac's Audio"
            }
        }
    }

    var track: RecognizedTrack?
    var providerName: String?
    var isAudioPresent = false
    var mode: Mode = .playerMetadata
    var errorMessage: String?

    private let monitor = PlayerMetadataMonitor()
    private var capture: (any AudioCaptureService)?
    private var recognizer: (any TrackRecognizing)?

    init() {
        monitor.onSnapshot = { [weak self] snapshot in
            self?.track = snapshot?.track
            self?.providerName = snapshot?.provider.rawValue
            self?.isAudioPresent = snapshot != nil
        }
    }

    func start() async {
        errorMessage = nil
        await stop()
        switch mode {
        case .playerMetadata:
            monitor.start()
        case .microphone:
            await startAudio(source: .microphone)
        case .systemAudio:
            await startAudio(source: .systemAudio)
        }
    }

    func stop() async {
        monitor.stop()
        let activeCapture = capture
        capture = nil
        activeCapture?.onFrame = nil
        activeCapture?.onFailure = nil
        await activeCapture?.stop()
        recognizer?.invalidate()
        recognizer = nil
        isAudioPresent = false
    }

    private func startAudio(source: CaptureSource) async {
        let newCapture: any AudioCaptureService = source == .microphone ? MicrophoneAudioCapture() : SystemAudioCapture()
        let newRecognizer: any TrackRecognizing = ShazamRecognizer()
        newRecognizer.onMatch = { [weak self] value in
            Task { @MainActor in
                self?.track = value
                self?.providerName = source == .microphone ? "Shazam · Around Me" : "Shazam · This Mac"
            }
        }
        newRecognizer.onError = { _ in }
        newCapture.onFrame = { [weak self, weak newRecognizer] frame in
            newRecognizer?.process(frame.buffer, at: frame.time)
            Task { @MainActor in self?.isAudioPresent = frame.isAudible }
        }
        newCapture.onFailure = { [weak self] message in Task { @MainActor in self?.errorMessage = message } }
        capture = newCapture
        recognizer = newRecognizer
        do { try await newCapture.start() }
        catch { errorMessage = error.localizedDescription }
    }
}
