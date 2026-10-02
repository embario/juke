@preconcurrency import AVFoundation
import Foundation

struct CapturedAudioFrame: @unchecked Sendable {
    let buffer: AVAudioPCMBuffer
    let time: AVAudioTime?
    let isAudible: Bool
}

protocol AudioCaptureService: AnyObject, Sendable {
    var onFrame: (@Sendable (CapturedAudioFrame) -> Void)? { get set }
    var onFailure: (@Sendable (String) -> Void)? { get set }

    func start() async throws
    func stop() async
}

enum AudioLevelMeter {
    static func isAudible(_ buffer: AVAudioPCMBuffer) -> Bool {
        guard let channels = buffer.floatChannelData, buffer.frameLength > 0 else {
            // Interleaved integer buffers are still valid music input; ShazamKit
            // receives them even though this lightweight meter cannot inspect them.
            return true
        }
        let samples = channels[0]
        let count = Int(buffer.frameLength)
        var sum: Float = 0
        for index in stride(from: 0, to: count, by: 16) {
            let value = samples[index]
            sum += value * value
        }
        let inspected = max(1, count / 16)
        return sqrt(sum / Float(inspected)) > 0.002
    }
}
