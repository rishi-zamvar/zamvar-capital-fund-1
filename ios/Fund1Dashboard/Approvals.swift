import Fund1Kit
import SwiftUI

struct ApprovalsView: View {
    let vm: ApprovalsViewModel
    let openSettings: () -> Void

    var body: some View {
        NavigationStack {
            StateView(state: vm.state, retry: vm.load, openSettings: openSettings) { items in
                if items.isEmpty {
                    ContentUnavailableView("No pending decisions", systemImage: "checkmark.seal",
                                           description: Text("No pending decisions — the desk submits after a T-2 run."))
                        .refreshableList { await vm.load() }
                } else {
                    List(items) { d in
                        NavigationLink {
                            DossierView(summary: d, vm: vm)
                        } label: {
                            LabeledContent {
                                Text(d.sizePct.or(\.pct)).monospacedDigit()
                            } label: {
                                Text(d.ticker ?? "#\(d.id)").font(.headline)
                                Text("entry \(d.entry.or(\.price)) · exit by \(d.exitBy ?? "—")").font(.caption).monospacedDigit()
                            }
                        }
                    }
                    .refreshable { await vm.load() }
                }
            }
            .navigationTitle("Approvals")
            .toolbar { SettingsButton(action: openSettings) }
        }
    }
}

private extension View {
    func refreshableList(_ action: @escaping @Sendable () async -> Void) -> some View {
        List { self.listRowBackground(Color.clear) }.refreshable(action: action)
    }
}

/// The review screen. Approve / Reject are reachable ONLY through a confirmationDialog — no swipe,
/// no default action, no auto-approve.
struct DossierView: View {
    let summary: DecisionSummary
    let vm: ApprovalsViewModel
    @State private var dossier: Loader<Dossier>
    @State private var confirming: Action?
    @State private var working = false
    @Environment(\.dismiss) private var dismiss

    enum Action: String, Identifiable { case approve, reject; var id: String { rawValue } }

    init(summary: DecisionSummary, vm: ApprovalsViewModel) {
        self.summary = summary
        self.vm = vm
        let client = vm.client
        let id = summary.id
        _dossier = State(initialValue: Loader { try await client.dossier(id: id) })
    }

    var ticker: String { summary.ticker ?? "#\(summary.id)" }
    var size: String { summary.sizePct.or(\.pct) }

    var body: some View {
        StateView(state: dossier.state, retry: dossier.load, openSettings: {}) { d in
            DossierContent(d: d)
        }
        .navigationTitle(ticker)
        .navigationBarTitleDisplayMode(.inline)
        .task { await dossier.load() }
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: 6) {
                if let e = vm.actionError { Text(e).font(.caption).foregroundStyle(.red) }
                HStack {
                    Button("Reject", role: .destructive) { confirming = .reject }
                        .buttonStyle(.bordered).frame(maxWidth: .infinity)
                    Button("Approve") { confirming = .approve }
                        .buttonStyle(.borderedProminent).frame(maxWidth: .infinity)
                }
                .controlSize(.large)
                .disabled(working || summary.status != "pending")
            }
            .padding().background(.bar)
        }
        .confirmationDialog(confirming == .approve ? "Approve \(ticker)?" : "Reject \(ticker)?",
                            isPresented: Binding(get: { confirming != nil }, set: { if !$0 { confirming = nil } }),
                            titleVisibility: .visible, presenting: confirming) { action in
            switch action {
            case .approve: Button("Open paper position") { run(action) }
            case .reject: Button("Reject decision", role: .destructive) { run(action) }
            }
            Button("Cancel", role: .cancel) {}
        } message: { action in
            switch action {
            case .approve: Text("Open a PAPER position in \(ticker) at \(size)? Nothing opens until you confirm.")
            case .reject: Text("Reject the \(ticker) decision at \(size)? No position will open.")
            }
        }
    }

    func run(_ action: Action) {
        working = true
        Task {
            let ok = action == .approve ? await vm.approve(id: summary.id) : await vm.reject(id: summary.id)
            working = false
            if ok { dismiss() }
        }
    }
}

struct DossierContent: View {
    let d: Dossier

    var body: some View {
        let trade = d.review?.dossier?.trade
        List {
            Section("Trade") {
                LabeledContent("Entry", value: (trade?.entry ?? d.entry).or(\.price))
                LabeledContent("Size", value: (trade?.sizePct ?? d.sizePct).or(\.pct))
                LabeledContent("Exit by", value: trade?.exitByDate ?? d.exitBy ?? "—")
                if let h = trade?.hedge?.ticker { LabeledContent("Hedge", value: h) }
                if trade?.stopLoss != nil || trade?.takeProfit != nil {
                    LabeledContent(trade?.slAdvisory == true ? "SL / TP (advisory — gap risk)" : "SL / TP",
                                   value: "\(trade?.stopLoss.or(\.price) ?? "—") / \(trade?.takeProfit.or(\.price) ?? "—")")
                }
                if let e = trade?.expectedReturnPct { LabeledContent("Expected return", value: e.signedPct) }
            }
            .monospacedDigit()

            if let review = d.review {
                if let s = review.dossier {
                    Section("Thesis") {
                        if let v = s.verdictSummary { Text(v) }
                        if let m = s.positionMemo { Text(m).font(.subheadline).foregroundStyle(.secondary) }
                    }
                    Section("Kill criteria") { Bullets(title: "", items: s.killCriteria ?? []) }
                    Section("Pre-mortem") { Bullets(title: "", items: s.preMortem ?? []) }
                }
                if let dd = review.dd {
                    Section("Due diligence") {
                        LabeledContent("Verdict", value: dd.verdict?.uppercased() ?? "—")
                        Bullets(title: "Red flags", items: dd.redFlags ?? [])
                        if let s = dd.strongestDisconfirmingEvidence {
                            VStack(alignment: .leading) {
                                Text("Strongest disconfirming evidence").font(.caption).foregroundStyle(.secondary)
                                Text(s)
                            }
                        }
                    }
                }
                if let md = review.decision {
                    Section("MD decision") {
                        LabeledContent("Decision", value: md.decision ?? "—")
                        if let r = md.rationale { Text(r) }
                        Bullets(title: "Accepted residuals", items: md.acceptedResiduals ?? [])
                        Bullets(title: "Preserved dissent", items: md.dissentPreserved ?? [])
                    }
                }
                let refs = Array(Set((review.dossier?.allEvidenceRefs ?? []) + (review.dd?.allEvidenceRefs ?? []))).sorted()
                if !refs.isEmpty {
                    Section("Evidence") { ForEach(refs, id: \.self) { EvidenceRow(ref: $0) } }
                }
            } else {
                ContentUnavailableView("No review snapshot", systemImage: "doc.questionmark",
                                       description: Text("This decision was submitted before review snapshots were stored."))
            }
        }
    }
}

struct EvidenceRow: View {
    let ref: String

    var body: some View {
        if let url = URL(string: ref), url.scheme?.hasPrefix("http") == true {
            Link(destination: url) { Label(ref, systemImage: "safari").lineLimit(1) }
                .contextMenu { Button("Copy", systemImage: "doc.on.doc") { UIPasteboard.general.string = ref } }
        } else {
            Button { UIPasteboard.general.string = ref } label: { Label(ref, systemImage: "doc.on.doc") }
                .foregroundStyle(.primary)
        }
    }
}
