import SwiftUI
import WebKit

struct WorldFocus: Equatable {
    let lat: Double
    let lng: Double
    let username: String?
}

struct JukeWorldView: View {
    @EnvironmentObject private var session: SessionStore
    @Environment(\.dismiss) private var dismiss
    let focus: WorldFocus?
    let onExit: (() -> Void)?
    @State private var isLoading = true

    init(focus: WorldFocus? = nil, onExit: (() -> Void)? = nil) {
        self.focus = focus
        self.onExit = onExit
    }

    var body: some View {
        NavigationStack {
            ZStack {
                JukeWorldWebView(
                    token: session.token ?? "",
                    focus: focus,
                    isLoading: $isLoading,
                    onExit: onExit
                )
                    .edgesIgnoringSafeArea(.all)
                if isLoading {
                    Color.black
                        .ignoresSafeArea()
                    ProgressView("Loading Juke World...")
                        .tint(JukePalette.accent)
                        .foregroundColor(.white)
                }
            }
            .navigationTitle("Juke World")
            .navigationBarTitleDisplayMode(.inline)
            .navigationBarBackButtonHidden(true)
            .modifier(DisableBackSwipe())
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button(action: handleExit) {
                        HStack(spacing: 6) {
                            Image(systemName: "chevron.left")
                            Text("Home")
                        }
                        .tint(JukePalette.accent)
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: session.logout) {
                        Image(systemName: "rectangle.portrait.and.arrow.right")
                            .tint(JukePalette.accent)
                    }
                }
            }
        }
    }

    private func handleExit() {
        onExit?()
        dismiss()
    }
}

private struct DisableBackSwipe: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(BackSwipeDisabler())
    }
}

private struct BackSwipeDisabler: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> UIViewController {
        Controller()
    }

    func updateUIViewController(_ uiViewController: UIViewController, context: Context) {}

    private final class Controller: UIViewController {
        override func viewDidAppear(_ animated: Bool) {
            super.viewDidAppear(animated)
            navigationController?.interactivePopGestureRecognizer?.isEnabled = false
        }

        override func viewWillDisappear(_ animated: Bool) {
            super.viewWillDisappear(animated)
            navigationController?.interactivePopGestureRecognizer?.isEnabled = true
        }
    }
}

/// UIKit WebView wrapper that injects the auth token into localStorage
/// so the web app's AuthProvider recognises the session.
private struct JukeWorldWebView: UIViewRepresentable {
    let token: String
    let focus: WorldFocus?
    @Binding var isLoading: Bool
    let onExit: (() -> Void)?

    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView(frame: .zero, configuration: context.coordinator.webViewConfig)
        webView.navigationDelegate = context.coordinator
        webView.isOpaque = false
        webView.backgroundColor = UIColor.black
        webView.scrollView.backgroundColor = UIColor.black
        webView.scrollView.bounces = false
        context.coordinator.webView = webView

        let baseUrl = APIConfiguration.shared.frontendURL.appendingPathComponent("world")
        var components = URLComponents(url: baseUrl, resolvingAgainstBaseURL: false)
        var queryItems: [URLQueryItem] = []
        queryItems.append(URLQueryItem(name: "native", value: "1"))
        if let focus {
            queryItems.append(URLQueryItem(name: "welcome", value: "1"))
            queryItems.append(URLQueryItem(name: "focusLat", value: String(focus.lat)))
            queryItems.append(URLQueryItem(name: "focusLng", value: String(focus.lng)))
            if let username = focus.username, !username.isEmpty {
                queryItems.append(URLQueryItem(name: "focusUsername", value: username))
            }
        }
        if !queryItems.isEmpty {
            components?.queryItems = queryItems
        }
        let url = components?.url ?? baseUrl
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        // Re-inject token if it changed (e.g., after silent refresh)
        context.coordinator.updateToken(token)
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(token: token, setLoading: { isLoading = $0 }, onExit: onExit)
    }

    class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        private(set) var token: String
        weak var webView: WKWebView?
        let webViewConfig: WKWebViewConfiguration
        private let userContentController: WKUserContentController
        private let setLoading: (Bool) -> Void
        private let onExit: (() -> Void)?

        init(token: String, setLoading: @escaping (Bool) -> Void, onExit: (() -> Void)?) {
            self.token = token
            self.setLoading = setLoading
            self.onExit = onExit
            self.userContentController = WKUserContentController()
            self.webViewConfig = WKWebViewConfiguration()
            self.webViewConfig.userContentController = userContentController
            super.init()
            updateUserScript()
            userContentController.add(self, name: "jukeWorld")
        }

        func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
            DispatchQueue.main.async {
                self.setLoading(true)
            }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            injectToken(token)
            DispatchQueue.main.async {
                self.setLoading(false)
            }
        }

        func updateToken(_ token: String) {
            self.token = token
            updateUserScript()
            injectToken(token)
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "jukeWorld" else { return }
            if let body = message.body as? [String: Any],
               let type = body["type"] as? String,
               type == "exit" {
                DispatchQueue.main.async {
                    self.onExit?()
                }
            }
        }

        func injectToken(_ token: String) {
            guard let webView else { return }
            let payload = "{\"token\":\"\(escapeForJavaScript(token))\"}"
            let script = "localStorage.setItem('juke-auth-state', '\(payload)');"
            webView.evaluateJavaScript(script, completionHandler: nil)
        }

        private func updateUserScript() {
            userContentController.removeAllUserScripts()
            let payload = "{\"token\":\"\(escapeForJavaScript(token))\"}"
            let source = "localStorage.setItem('juke-auth-state', '\(payload)');"
            let script = WKUserScript(source: source, injectionTime: .atDocumentStart, forMainFrameOnly: true)
            userContentController.addUserScript(script)
        }

        private func escapeForJavaScript(_ value: String) -> String {
            value
                .replacingOccurrences(of: "\\", with: "\\\\")
                .replacingOccurrences(of: "'", with: "\\'")
        }
    }
}
