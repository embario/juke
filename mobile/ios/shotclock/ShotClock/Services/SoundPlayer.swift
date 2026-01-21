import AVFoundation

final class SoundPlayer {
    static let shared = SoundPlayer()

    private var player: AVAudioPlayer?

    func play(_ name: String) {
        guard let url = Bundle.main.url(forResource: name, withExtension: "wav") else { return }
        do {
            player = try AVAudioPlayer(contentsOf: url)
            player?.play()
        } catch {
            // Silent failure for preview sounds
        }
    }

    func stop() {
        player?.stop()
        player = nil
    }
}
