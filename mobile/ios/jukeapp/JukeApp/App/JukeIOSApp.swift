import SwiftData
import SwiftUI

@main
struct JukeIOSApp: App {
    private let container: ModelContainer
    @State private var model: VibeAppModel

    init() {
        do {
            let schema = Schema([EncryptedChatMessage.self])
            let testing = ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil
            let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            try FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
            let configuration = testing
                ? ModelConfiguration("JukeAppTests", schema: schema, isStoredInMemoryOnly: true)
                : ModelConfiguration("JukeApp", schema: schema, url: support.appending(path: "JukeApp.store"), cloudKitDatabase: .none)
            let container = try ModelContainer(for: schema, configurations: [configuration])
            self.container = container; _model = State(initialValue: VibeAppModel(container: container))
        } catch { fatalError("Unable to open Juke's private store: \(error.localizedDescription)") }
    }

    var body: some Scene {
        WindowGroup { RootView().environment(model).modelContainer(container) }
    }
}
