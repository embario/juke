// swift-tools-version: 5.9
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "JukeKit",
    platforms: [
        .iOS(.v16),
        .macOS(.v13)  // For testing with swift build/test
    ],
    products: [
        .library(
            name: "JukeKit",
            targets: ["JukeKit"]
        ),
    ],
    dependencies: [],
    targets: [
        .target(
            name: "JukeKit",
            dependencies: [],
            path: "Sources/JukeKit"
        ),
        .testTarget(
            name: "JukeKitTests",
            dependencies: ["JukeKit"],
            path: "Tests/JukeKitTests"
        ),
    ]
)
