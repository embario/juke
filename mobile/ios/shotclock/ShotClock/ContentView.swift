import SwiftUI
import JukeCore

struct ContentView: View {
    @EnvironmentObject var session: JukeSessionStore

    var body: some View {
        Group {
            if session.token != nil {
                HomeView()
            } else {
                AuthView(session: session)
            }
        }
        .animation(.easeInOut(duration: 0.3), value: session.token)
    }
}

#Preview {
    ContentView()
        .environmentObject(JukeSessionStore(keyPrefix: "shotclock"))
}
