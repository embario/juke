//
//  ContentView.swift
//  juke-iOS
//
//  Created by Mario Barrenechea on 3/28/22.
//

import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var session: SessionStore

    let verifyParams: (userId: String, timestamp: String, signature: String)?

    init(verifyParams: (userId: String, timestamp: String, signature: String)? = nil) {
        self.verifyParams = verifyParams
    }

    @State private var navigateToWorld = false
    @State private var worldFocus: WorldFocus? = nil

    var body: some View {
        Group {
            if let params = verifyParams {
                // Deep-link opened — show verification screen
                VerifyEmailView(
                    userId: params.userId,
                    timestamp: params.timestamp,
                    signature: params.signature
                )
            } else if session.isAuthenticated {
                if session.isLoadingProfile {
                    ProgressView("Loading profile...")
                } else if session.profile?.onboardingCompletedAt == nil {
                    OnboardingWizardView(
                        userKey: session.username ?? session.profile?.username ?? session.token,
                        navigateToWorld: $navigateToWorld,
                        worldFocus: $worldFocus
                    )
                } else if navigateToWorld {
                    JukeWorldView(focus: worldFocus, onExit: { navigateToWorld = false })
                        .onDisappear {
                            navigateToWorld = false
                            worldFocus = nil
                        }
                } else {
                    SearchDashboardView(session: session)
                }
            } else {
                AuthView(session: session)
            }
        }
        .animation(.easeInOut, value: session.isAuthenticated)
        .environmentObject(session)
    }
}

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
            .environmentObject(SessionStore())
    }
}
