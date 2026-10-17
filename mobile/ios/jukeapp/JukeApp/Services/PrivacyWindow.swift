import SwiftUI
import UIKit

/// Blurs everything, sheets included, while the scene is not active so the app
/// switcher snapshot and screen recordings never show private content. It is a
/// separate window above the app's, because sheets render above any SwiftUI overlay.
@MainActor
final class PrivacyWindow {
    private var window: UIWindow?

    static func shouldShield(phase: ScenePhase, signedIn: Bool) -> Bool { signedIn && phase != .active }

    func update(shielded: Bool) {
        shielded ? show() : hide()
    }

    private func show() {
        guard window == nil,
              let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first else { return }
        let window = UIWindow(windowScene: scene)
        window.windowLevel = .alert + 1
        let controller = UIViewController()
        let blur = UIVisualEffectView(effect: UIBlurEffect(style: .systemThickMaterial))
        blur.frame = controller.view.bounds
        blur.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        blur.isAccessibilityElement = false
        controller.view.addSubview(blur)
        window.rootViewController = controller
        window.isHidden = false
        self.window = window
    }

    private func hide() {
        window?.isHidden = true
        window = nil
    }
}
