import SwiftUI

struct ContentView: View {
    @EnvironmentObject var session: SessionStore

    var body: some View {
        Group {
            if session.token != nil {
                HomeView()
            } else {
                AuthView()
            }
        }
        .animation(.easeInOut(duration: 0.3), value: session.token)
    }
}

#Preview {
    ContentView()
        .environmentObject(SessionStore())
}
