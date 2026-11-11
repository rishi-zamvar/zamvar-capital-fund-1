import Charts
import Fund1Kit
import SwiftUI

// MARK: - This Week

struct WeekView: View {
    let vm: Loader<Week>
    let openSettings: () -> Void

    var body: some View {
        NavigationStack {
            StateView(state: vm.state, retry: vm.load, openSettings: openSettings) { w in
                List {
                    Section { header(w) }
                    Section("Upcoming catalysts") {
                        if w.upcoming.isEmpty { Text("No catalysts in the next 7 days").foregroundStyle(.secondary) }
                        ForEach(w.upcoming) { c in
                            LabeledContent {
                                Text(c.daysUntil == 0 ? "today" : "in \(c.daysUntil) day\(c.daysUntil == 1 ? "" : "s")")
                            } label: {
                                Text(c.ticker).font(.headline)
                                Text(c.catalystType.uppercased()).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                    Section("Open positions") {
                        if w.positions.isEmpty { Text("No open positions").foregroundStyle(.secondary) }
                        ForEach(w.positions) { PositionRow(p: $0) }
                    }
                }
                .refreshable { await vm.load() }
            }
            .navigationTitle("This Week")
            .toolbar { SettingsButton(action: openSettings) }
        }
        .task { await vm.load() }
    }

    func header(_ w: Week) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Gauge(value: min(max(w.expectedReturn ?? 0, 0), w.benchmarkWeekly * 2), in: 0...(w.benchmarkWeekly * 2)) {
                Text("Expected book return")
            } currentValueLabel: {
                Text(w.expectedReturn.or(\.signedPct)).monospacedDigit()
            } minimumValueLabel: { Text("0") } maximumValueLabel: { Text((w.benchmarkWeekly * 2).pct) }
            Text("Benchmark \(w.benchmarkWeekly.pct)/week").font(.caption).foregroundStyle(.secondary)
            HStack {
                LabeledContent("Sharpe", value: w.sharpe.or { $0.formatted(.number.precision(.fractionLength(2))) })
                Divider()
                LabeledContent("Expectancy", value: w.expectancy.or(\.signedPct))
            }
            .monospacedDigit()
        }
    }
}

struct PositionRow: View {
    let p: Position

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(p.ticker).font(.headline)
                if let h = p.hedgeTicker { Text("hedge \(h)").font(.caption).foregroundStyle(.secondary) }
                Spacer()
                if let r = p.unrealizedRet { Text(r.signedPct).foregroundStyle(r.gainColor).monospacedDigit() }
            }
            Text("\(p.entryPrice.price) → \(p.markPrice.or(\.price)) · size \(p.sizePct.pct) · exit by \(p.exitBy)")
                .font(.subheadline).monospacedDigit()
            if p.distToSl != nil || p.distToTp != nil {
                HStack {
                    Text("to SL \(p.distToSl.or(\.pct)) · to TP \(p.distToTp.or(\.pct))").monospacedDigit()
                    if p.slAdvisory == true { Text("advisory").font(.caption2).padding(.horizontal, 4).background(.quaternary, in: .capsule) }
                }
                .font(.caption)
            }
            if let t = p.thesis {
                DisclosureGroup("Thesis & risk") {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(t)
                        Bullets(title: "Kill criteria", items: p.killCriteria)
                        Bullets(title: "Pre-mortem failure factors", items: p.failureFactors)
                        Bullets(title: "Mitigations (accepted residuals)", items: p.mitigations)
                    }
                    .font(.subheadline)
                }
                .font(.caption)
            }
        }
    }
}

struct Bullets: View {
    let title: String
    let items: [String]

    var body: some View {
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.caption).foregroundStyle(.secondary)
                ForEach(items, id: \.self) { Text("• \($0)") }
            }
        }
    }
}

// MARK: - History

struct HistoryView: View {
    let vm: Loader<History>
    let openSettings: () -> Void

    var body: some View {
        NavigationStack {
            StateView(state: vm.state, retry: vm.load, openSettings: openSettings) { h in
                List {
                    if h.trades.isEmpty {
                        ContentUnavailableView("No closed trades yet", systemImage: "chart.line.uptrend.xyaxis",
                                               description: Text("The equity curve starts after the first position closes."))
                    } else {
                        Section("Equity curve") {
                            Chart {
                                ForEach(h.equityCurve) { LineMark(x: .value("Date", $0.date), y: .value("Equity", $0.equity)) }
                                RuleMark(y: .value("Start", 1.0)).foregroundStyle(.secondary).lineStyle(StrokeStyle(dash: [4]))
                            }
                            .chartYScale(domain: .automatic(includesZero: false))
                            .frame(height: 180)
                            HStack {
                                LabeledContent("Win rate", value: h.winRate.or(\.pct))
                                Divider()
                                LabeledContent("Trades", value: "\(h.trades.count)")
                                Divider()
                                LabeledContent("Sharpe", value: h.sharpe.or { $0.formatted(.number.precision(.fractionLength(2))) })
                            }
                            .monospacedDigit().font(.caption)
                        }
                        if !h.calibration.isEmpty {
                            Section("Calibration — predicted vs realized") {
                                Chart {
                                    ForEach(h.calibration) {
                                        PointMark(x: .value("Predicted", $0.predicted), y: .value("Realized", $0.realized))
                                    }
                                    let lo = h.calibration.flatMap { [$0.predicted, $0.realized] }.min() ?? 0
                                    let hi = h.calibration.flatMap { [$0.predicted, $0.realized] }.max() ?? 0
                                    LineMark(x: .value("Predicted", lo), y: .value("Realized", lo), series: .value("ref", "y=x"))
                                        .foregroundStyle(.secondary)
                                    LineMark(x: .value("Predicted", hi), y: .value("Realized", hi), series: .value("ref", "y=x"))
                                        .foregroundStyle(.secondary)
                                }
                                .frame(height: 180)
                            }
                        }
                        Section("Trades") {
                            ForEach(h.trades) { t in
                                LabeledContent {
                                    Text(t.realizedRet.signedPct).foregroundStyle(t.realizedRet.gainColor).monospacedDigit()
                                } label: {
                                    Text(t.ticker).font(.headline)
                                    Text("\(t.openedAt) → \(t.closedAt.map { String($0.prefix(10)) } ?? t.exitBy) · book \(t.bookRet.signedPct)")
                                        .font(.caption).monospacedDigit()
                                }
                            }
                        }
                    }
                    Section("Attribution") {
                        if let a = h.attribution {
                            ForEach(a.sorted(by: { $0.key < $1.key }), id: \.key) { LabeledContent($0.key, value: $0.value.signedPct) }
                        } else {
                            ContentUnavailableView("Attribution pending", systemImage: "hourglass",
                                                   description: Text("Catalyst / beta / hedge / sizing decomposition arrives with Phase 8."))
                        }
                    }
                }
                .refreshable { await vm.load() }
            }
            .navigationTitle("History")
            .toolbar { SettingsButton(action: openSettings) }
        }
        .task { await vm.load() }
    }
}

// MARK: - Playbook

struct PlaybookView: View {
    let vm: Loader<PlaybookResponse>
    let openSettings: () -> Void

    var body: some View {
        NavigationStack {
            StateView(state: vm.state, retry: vm.load, openSettings: openSettings) { r in
                if r.playbooks.isEmpty {
                    ContentUnavailableView("No playbooks yet", systemImage: "book",
                                           description: Text("The warm start writes playbooks into the KB."))
                } else {
                    List {
                        ForEach(Dictionary(grouping: r.playbooks, by: \.scenarioType).sorted(by: { $0.key < $1.key }), id: \.key) { type, items in
                            Section(type.replacingOccurrences(of: "_", with: " ").capitalized) {
                                ForEach(items) { PlaybookRow(p: $0) }
                            }
                        }
                    }
                    .refreshable { await vm.load() }
                }
            }
            .navigationTitle("Playbook")
            .toolbar { SettingsButton(action: openSettings) }
        }
        .task { await vm.load() }
    }
}

struct PlaybookRow: View {
    let p: Playbook

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(p.scenario).font(.headline)
            if let c = p.confidence {
                ProgressView(value: c) { Text("Confidence \(c.formatted(.percent.precision(.fractionLength(0))))").font(.caption) }
            }
            if let s = p.strategyText { Text(s).font(.subheadline) }
            if let n = p.n { Text("n = \(n) · median move \(p.medianMove.or(\.signedPct))").font(.caption).monospacedDigit() }
            ForEach(p.baseRate, id: \.label) { LabeledContent($0.label, value: $0.rate.pct).font(.caption) }
            Bullets(title: "What to watch", items: p.whatToWatch).font(.caption)
        }
    }
}

// MARK: - MD Chat

struct ChatView: View {
    @Bindable var vm: ChatViewModel

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                List(vm.messages) { m in
                    Text(m.text.isEmpty ? "…" : m.text)
                        .foregroundStyle(m.isError ? .red : .primary)
                        .frame(maxWidth: .infinity, alignment: m.fromUser ? .trailing : .leading)
                        .listRowSeparator(.hidden)
                        .id(m.id)
                }
                .listStyle(.plain)
                .overlay {
                    if vm.messages.isEmpty {
                        ContentUnavailableView("Ask the MD", systemImage: "bubble.left.and.bubble.right",
                                               description: Text("Positioning, rationale and risk — the MD explains; only you approve."))
                    }
                }
                .onChange(of: vm.messages.last?.text) { if let id = vm.messages.last?.id { proxy.scrollTo(id, anchor: .bottom) } }
            }
            .safeAreaInset(edge: .bottom) {
                HStack {
                    TextField("Ask about the book", text: $vm.draft, axis: .vertical).textFieldStyle(.roundedBorder)
                    Button("Send", systemImage: "arrow.up.circle.fill") { Task { await vm.send() } }
                        .labelStyle(.iconOnly).font(.title2)
                        .disabled(vm.isStreaming || vm.draft.trimmingCharacters(in: .whitespaces).isEmpty)
                }
                .padding().background(.bar)
            }
            .navigationTitle("MD Chat")
        }
    }
}
