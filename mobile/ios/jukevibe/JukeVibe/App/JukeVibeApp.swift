import SwiftData
import SwiftUI

@main
struct JukeVibeApp: App {
    private let container: ModelContainer
    @State private var model: VibeAppModel

    init() {
        do {
            let schema = Schema([EncryptedChatMessage.self])
            let testing = ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil
            let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            try FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
            let configuration = testing
                ? ModelConfiguration("JukeVibeTests", schema: schema, isStoredInMemoryOnly: true)
                : ModelConfiguration("JukeVibe", schema: schema, url: support.appending(path: "JukeVibe.store"), cloudKitDatabase: .none)
            let container = try ModelContainer(for: schema, configurations: [configuration])
            self.container = container; _model = State(initialValue: VibeAppModel(container: container))
        } catch { fatalError("Unable to open Juke Vibe's private store: \(error.localizedDescription)") }
    }

    var body: some Scene {
        WindowGroup { RootView().environment(model).modelContainer(container) }
    }
}
