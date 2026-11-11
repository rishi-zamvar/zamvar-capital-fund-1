import Fund1Kit
import Security
import SwiftUI

@main
struct Fund1DashboardApp: App {
    var body: some Scene { WindowGroup { RootView() } }
}

/// The bearer token lives in the Keychain, never UserDefaults.
enum Keychain {
    static let account = "dashboard-token"
    static let service = "com.rishizamvar.fund1dashboard"

    static func read() -> String? {
        var out: AnyObject?
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: account, kSecReturnData as String: true]
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data else { return nil }
        return String(data: d, encoding: .utf8)
    }

    static func write(_ token: String) {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: account]
        SecItemDelete(q as CFDictionary)
        var add = q
        add[kSecValueData as String] = Data(token.utf8)
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(add as CFDictionary, nil)
    }
}

struct RootView: View {
    @AppStorage("serverURL") private var serverURL = "http://127.0.0.1:8790"
    @State private var token = Keychain.read() ?? ""
    @State private var showSettings = false
    @State private var generation = 0

    var client: any DashboardClient {
        APIClient(baseURL: URL(string: serverURL) ?? URL(string: "http://127.0.0.1:8790")!, token: token)
    }

    var body: some View {
        Tabs(client: client, openSettings: { showSettings = true })
            .id(generation)  // rebuild every screen with the new client after Settings changes
            .tint(Color.accentColor)
            .sheet(isPresented: $showSettings) {
                SettingsView(serverURL: $serverURL, token: $token) { generation += 1 }
            }
            .onAppear { if token.isEmpty { showSettings = true } }
    }
}

struct Tabs: View {
    let openSettings: () -> Void
    @State private var week: Loader<Week>
    @State private var history: Loader<History>
    @State private var playbook: Loader<PlaybookResponse>
    @State private var approvals: ApprovalsViewModel
    @State private var chat: ChatViewModel

    init(client: any DashboardClient, openSettings: @escaping () -> Void) {
        self.openSettings = openSettings
        _week = State(initialValue: Loader { try await client.week() })
        _history = State(initialValue: Loader { try await client.history() })
        _playbook = State(initialValue: Loader { try await client.playbook() })
        _approvals = State(initialValue: ApprovalsViewModel(client: client))
        _chat = State(initialValue: ChatViewModel(client: client))
    }

    var body: some View {
        TabView {
            WeekView(vm: week, openSettings: openSettings).tabItem { Label("This Week", systemImage: "calendar") }
            HistoryView(vm: history, openSettings: openSettings)
                .tabItem { Label("History", systemImage: "chart.line.uptrend.xyaxis") }
            PlaybookView(vm: playbook, openSettings: openSettings).tabItem { Label("Playbook", systemImage: "book") }
            ApprovalsView(vm: approvals, openSettings: openSettings)
                .tabItem { Label("Approvals", systemImage: "checkmark.seal") }
                .badge(approvals.state.value?.count ?? 0)
            ChatView(vm: chat).tabItem { Label("MD Chat", systemImage: "bubble.left.and.bubble.right") }
        }
        .task { await approvals.load() }
    }
}

struct SettingsView: View {
    @Binding var serverURL: String
    @Binding var token: String
    let onSave: () -> Void
    @State private var draftURL = ""
    @State private var draftToken = ""
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("http://100.x.y.z:8790", text: $draftURL)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                } header: { Text("Server") } footer: { Text("The dashboard shim over Tailscale (scripts/serve_dashboard.py).") }
                Section {
                    SecureField("DASHBOARD_TOKEN", text: $draftToken)
                } header: { Text("Token") } footer: { Text("Stored in the Keychain on this device only.") }
            }
            .navigationTitle("Settings")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        serverURL = draftURL.trimmingCharacters(in: .whitespaces)
                        token = draftToken.trimmingCharacters(in: .whitespaces)
                        Keychain.write(token)
                        onSave()
                        dismiss()
                    }
                    .disabled(URL(string: draftURL)?.scheme == nil || draftToken.isEmpty)
                }
            }
            .onAppear { draftURL = serverURL; draftToken = token }
        }
    }
}

// MARK: - shared state rendering + formatting

/// Loading / error / unauthorized / loaded for any screen.
struct StateView<T: Sendable & Equatable, Content: View>: View {
    let state: LoadState<T>
    let retry: () async -> Void
    let openSettings: () -> Void
    @ViewBuilder let content: (T) -> Content

    var body: some View {
        switch state {
        case .idle, .loading: ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        case .loaded(let v): content(v)
        case .unauthorized:
            ContentUnavailableView {
                Label("Not signed in", systemImage: "lock")
            } description: { Text("The server rejected the token.") } actions: {
                Button("Open Settings", action: openSettings).buttonStyle(.borderedProminent)
            }
        case .failed(let m):
            ContentUnavailableView {
                Label("Couldn't load", systemImage: "exclamationmark.triangle")
            } description: { Text(m) } actions: {
                Button("Retry") { Task { await retry() } }.buttonStyle(.bordered)
            }
        }
    }
}

extension Double {
    /// Signed percent: gains/losses always carry +/- (never colour-only).
    var signedPct: String { formatted(.percent.precision(.fractionLength(2)).sign(strategy: .always(includingZero: false))) }
    var pct: String { formatted(.percent.precision(.fractionLength(2))) }
    var price: String { formatted(.number.precision(.fractionLength(2))) }
    var gainColor: Color { self > 0 ? .green : self < 0 ? .red : .secondary }
}

extension Optional where Wrapped == Double {
    func or(_ f: (Double) -> String) -> String { map(f) ?? "—" }
}

struct SettingsButton: ToolbarContent {
    let action: () -> Void
    var body: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) { Button("Settings", systemImage: "gear", action: action) }
    }
}
