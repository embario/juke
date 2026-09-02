@preconcurrency import AVFoundation
import Foundation

final class MicrophoneAudioCapture: @unchecked Sendable, AudioCaptureService {
    var onFrame: (@Sendable (CapturedAudioFrame) -> Void)?
    var onFailure: (@Sendable (String) -> Void)?

    private let engine = AVAudioEngine()
    private var isStarted = false

    func start() async throws {
        let granted = await AVCaptureDevice.requestAccess(for: .audio)
        guard granted else { throw AudioCaptureError.permissionDenied(.microphone) }

        let input = engine.inputNode
        let format = input.inputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            throw AudioCaptureError.microphoneUnavailable
        }

        input.installTap(onBus: 0, bufferSize: 4_096, format: format) { [weak self] buffer, time in
            guard let self else { return }
            onFrame?(CapturedAudioFrame(
                buffer: buffer,
                time: time,
                isAudible: AudioLevelMeter.isAudible(buffer)
            ))
        }
        engine.prepare()
        do {
            try engine.start()
            isStarted = true
        } catch {
            input.removeTap(onBus: 0)
            throw error
        }
    }

    func stop() async {
        guard isStarted else { return }
        engine.stop()
        engine.inputNode.removeTap(onBus: 0)
        isStarted = false
    }
}
