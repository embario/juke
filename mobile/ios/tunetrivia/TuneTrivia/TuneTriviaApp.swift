//
//  TuneTriviaApp.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-22.
//

import SwiftUI

@main
struct TuneTriviaApp: App {
    @StateObject private var session = SessionStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(session)
        }
    }
}
