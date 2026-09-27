import SwiftData
import SwiftUI

@main
struct JukeVibeApp: App {
    private let container: ModelContainer
    @State private var model: AppModel

    init() {
        MemoryStore.removeStaleMedia()
        do {
            let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                .appending(path: "Juke Vibe", directoryHint: .isDirectory)
            try FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
            let schema = Schema([ChatMessage.self])
            let testing = ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil
                || ProcessInfo.processInfo.arguments.contains("--uitesting")
            let configuration = testing
                ? ModelConfiguration("JukeVibeTests", schema: schema, isStoredInMemoryOnly: true)
                : ModelConfiguration("JukeVibe", schema: schema, url: support.appending(path: "Vibe.store"), cloudKitDatabase: .none)
            let container = try ModelContainer(for: schema, configurations: [configuration])
            self.container = container
            _model = State(initialValue: AppModel(container: container))
        } catch { fatalError("Unable to open Juke Vibe's private store: \(error.localizedDescription)") }
    }

    var body: some Scene {
        Window("Juke Vibe", id: "main") {
            JukeVibeRootView()
                .environment(model)
                .modelContainer(container)
                .frame(minWidth: 900, minHeight: 640)
                .onOpenURL { url in Task { await model.completeAuthentication(url) } }
        }
        .windowResizability(.contentMinSize)

        Settings { VibeSettingsView().environment(model).frame(width: 520) }
    }
}
