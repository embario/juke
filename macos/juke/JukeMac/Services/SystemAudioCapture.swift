@preconcurrency import AVFoundation
@preconcurrency import CoreMedia
import CoreGraphics
import Foundation
@preconcurrency import ScreenCaptureKit

enum AudioCaptureError: LocalizedError {
    case noDisplay
    case unableToAttachOutput
    case permissionDenied(CaptureSource)
    case microphoneUnavailable

    var errorDescription: String? {
        switch self {
        case .noDisplay: "No display is available for system-audio capture."
        case .unableToAttachOutput: "Juke could not attach to the selected audio source."
        case .permissionDenied(let source):
            source == .systemAudio
                ? "Allow Screen & System Audio Recording in System Settings, then try again."
                : "Allow microphone access in System Settings, then try again."
        case .microphoneUnavailable: "No usable microphone is available."
        }
    }
}

final class SystemAudioCapture: NSObject, @unchecked Sendable, AudioCaptureService {
    var onFrame: (@Sendable (CapturedAudioFrame) -> Void)?
    var onFailure: (@Sendable (String) -> Void)?

    private let queue = DispatchQueue(label: "com.juke.mac.audio-capture", qos: .userInitiated)
    private var stream: SCStream?

    func start() async throws {
        guard CGPreflightScreenCaptureAccess() || CGRequestScreenCaptureAccess() else {
            throw AudioCaptureError.permissionDenied(.systemAudio)
        }
        let content = try await SCShareableContent.current
        guard let display = content.displays.first else { throw AudioCaptureError.noDisplay }

        let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])
        let configuration = SCStreamConfiguration()
        configuration.width = 2
        configuration.height = 2
        configuration.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        configuration.queueDepth = 3
        configuration.showsCursor = false
        configuration.capturesAudio = true
        configuration.captureMicrophone = false
        configuration.excludesCurrentProcessAudio = true
        configuration.sampleRate = 48_000
        configuration.channelCount = 2

        let stream = SCStream(filter: filter, configuration: configuration, delegate: self)
        do {
            try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: queue)
        } catch {
            throw AudioCaptureError.unableToAttachOutput
        }
        self.stream = stream
        try await stream.startCapture()
    }

    func stop() async {
        guard let stream else { return }
        do { try await stream.stopCapture() } catch { }
        self.stream = nil
    }

    private func makePCMBuffer(from sampleBuffer: CMSampleBuffer) -> AVAudioPCMBuffer? {
        guard sampleBuffer.isValid,
              CMSampleBufferDataIsReady(sampleBuffer),
              let description = CMSampleBufferGetFormatDescription(sampleBuffer),
              let basicDescription = CMAudioFormatDescriptionGetStreamBasicDescription(description) else {
            return nil
        }

        var streamDescription = basicDescription.pointee
        guard let format = AVAudioFormat(streamDescription: &streamDescription) else { return nil }
        let sampleCount = CMSampleBufferGetNumSamples(sampleBuffer)
        guard sampleCount > 0,
              let pcm = AVAudioPCMBuffer(
                pcmFormat: format,
                frameCapacity: AVAudioFrameCount(sampleCount)
              ) else { return nil }
        pcm.frameLength = AVAudioFrameCount(sampleCount)

        let status = CMSampleBufferCopyPCMDataIntoAudioBufferList(
            sampleBuffer,
            at: 0,
            frameCount: Int32(sampleCount),
            into: pcm.mutableAudioBufferList
        )
        return status == noErr ? pcm : nil
    }

}

extension SystemAudioCapture: SCStreamOutput, SCStreamDelegate {
    func stream(
        _ stream: SCStream,
        didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
        of outputType: SCStreamOutputType
    ) {
        guard outputType == .audio || outputType == .microphone,
              let buffer = makePCMBuffer(from: sampleBuffer) else { return }
        let presentationTime = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        let time = AVAudioTime(hostTime: 0, sampleTime: presentationTime.value, atRate: Double(presentationTime.timescale))
        onFrame?(CapturedAudioFrame(
            buffer: buffer,
            time: time,
            isAudible: AudioLevelMeter.isAudible(buffer)
        ))
    }

    func stream(_ stream: SCStream, didStopWithError error: any Error) {
        onFailure?(error.localizedDescription)
    }
}
