//
//  juke_iOSApp.swift
//  juke-iOS
//
//  Created by Mario Barrenechea on 3/28/22.
//

import SwiftUI
import JukeKit

@main
struct juke_iOSApp: App {
    @StateObject private var session = JukeSessionStore(keyPrefix: "juke")

    // Deep-link state for email verification
    @State private var verifyParams: (userId: String, timestamp: String, signature: String)? = nil

    private let deepLinkParser = JukeDeepLinkParser(
        schemes: ["juke"],
        universalLinkHosts: ["juke.fm", "www.juke.fm"]
    )

    var body: some Scene {
        WindowGroup {
            ContentView(verifyParams: verifyParams)
                .environmentObject(session)
                .onOpenURL { url in
                    handleDeepLink(url)
                }
        }
    }

    private func handleDeepLink(_ url: URL) {
        guard let deepLink = deepLinkParser.parse(url) else {
            return
        }

        switch deepLink {
        case .verifyUser(let userId, let timestamp, let signature):
            verifyParams = (userId: userId, timestamp: timestamp, signature: signature)
        case .register:
            // Juke app handles registration itself, no redirect needed
            break
        case .custom:
            // Handle other custom deep links if needed
            break
        }
    }
}
