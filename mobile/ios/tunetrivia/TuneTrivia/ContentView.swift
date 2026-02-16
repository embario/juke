//
//  ContentView.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-22.
//

import SwiftUI
import JukeKit

struct ContentView: View {
    @EnvironmentObject private var session: JukeSessionStore

    var body: some View {
        Group {
            if session.isAuthenticated {
                HomeView()
            } else {
                AuthView(session: session)
            }
        }
        .animation(.easeInOut(duration: 0.3), value: session.isAuthenticated)
    }
}

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
            .environmentObject(JukeSessionStore(keyPrefix: "tunetrivia"))
    }
}
