//
//  TuneTriviaApp.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-22.
//

import SwiftUI
import JukeCore

@main
struct TuneTriviaApp: App {
    @StateObject private var session = JukeSessionStore(keyPrefix: "tunetrivia")

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(session)
        }
    }
}
