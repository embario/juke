// swift-tools-version: 5.9
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "JukeCore",
    platforms: [
        .iOS(.v16),
        .macOS(.v13)  // For testing with swift build/test
    ],
    products: [
        .library(
            name: "JukeCore",
            targets: ["JukeCore"]
        ),
    ],
    dependencies: [],
    targets: [
        .target(
            name: "JukeCore",
            dependencies: [],
            path: "Sources/JukeCore"
        ),
        .testTarget(
            name: "JukeCoreTests",
            dependencies: ["JukeCore"],
            path: "Tests/JukeCoreTests"
        ),
    ]
)
