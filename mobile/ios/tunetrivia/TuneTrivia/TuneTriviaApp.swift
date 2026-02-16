//
//  TuneTriviaApp.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-22.
//

import SwiftUI
import JukeKit

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
