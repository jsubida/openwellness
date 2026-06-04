import SwiftUI
import Shared

@main
struct iOSApp: App {
    init() {
        // Base URL for the iOS build. Defaults to the simulator-friendly
        // localhost; override here (or via xcconfig/Info.plist) per environment.
        IosKoinKt.doInitKoin(baseUrl: "http://localhost:8000/v1/")
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
