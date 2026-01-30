//
//  juke_iOSApp.swift
//  juke-iOS
//
//  Created by Mario Barrenechea on 3/28/22.
//

import SwiftUI

@main
struct juke_iOSApp: App {
    @StateObject private var session = SessionStore()

    // Deep-link state for email verification
    @State private var verifyParams: (userId: String, timestamp: String, signature: String)? = nil

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
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            return
        }

        // Handle juke://verify-user?user_id=X&timestamp=Y&signature=Z
        // Also handle universal links: https://juke.fm/verify-user?...
        let host = components.host ?? ""
        let path = components.path ?? ""

        let isVerifyLink = host == "verify-user" || path == "/verify-user"

        guard isVerifyLink else { return }

        let params = components.queryParameters
        guard let userId = params["user_id"],
              let timestamp = params["timestamp"],
              let signature = params["signature"] else {
            return
        }

        verifyParams = (userId: userId, timestamp: timestamp, signature: signature)
    }
}

// MARK: - URL query parameter helper

extension URLComponents {
    var queryParameters: [String: String] {
        guard let queryItems = queryItems else { return [:] }
        return Dictionary(uniqueKeysWithValues: queryItems.compactMap { item in
            guard let value = item.value else { return nil }
            return (item.name, value)
        })
    }
}
