//
//  ContentView.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-22.
//

import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var session: SessionStore

    var body: some View {
        Group {
            if session.isAuthenticated {
                HomeView()
            } else {
                AuthView()
            }
        }
        .animation(.easeInOut(duration: 0.3), value: session.isAuthenticated)
    }
}

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
            .environmentObject(SessionStore())
    }
}
