// swift-tools-version: 6.0
// Fund1Kit — the dashboard's models, transport (HTTP + SSE) and view-models. No third-party deps.
// A package (not app-target sources) so `swift test` runs the unit tests on the Mac host without a
// simulator runtime; the iOS app target links it.
import PackageDescription

let package = Package(
    name: "Fund1Kit",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "Fund1Kit", targets: ["Fund1Kit"])],
    targets: [
        .target(name: "Fund1Kit"),
        .testTarget(name: "Fund1KitTests", dependencies: ["Fund1Kit"], resources: [.copy("Fixtures")]),
    ]
)
