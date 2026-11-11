import Foundation

// Mirrors src/catalyst_trader/dashboard_api.py payloads. Decoded with .convertFromSnakeCase, so every
// field name below is the camelCase of the server key. Optional = the server may send null (an honest
// empty state — never rendered as 0).

public struct Week: Codable, Sendable, Equatable {
    public var asOf: String
    public var benchmarkWeekly: Double
    public var expectedReturn: Double?
    public var sharpe: Double?
    public var expectancy: Double?
    public var pendingCount: Int
    public var upcoming: [UpcomingCatalyst]
    public var positions: [Position]
}

public struct UpcomingCatalyst: Codable, Sendable, Equatable, Identifiable {
    public var ticker: String
    public var catalystType: String
    public var eventDate: String
    public var daysUntil: Int
    public var id: String { "\(ticker)-\(eventDate)" }
}

public struct Position: Codable, Sendable, Equatable, Identifiable {
    public var id: Int
    public var ticker: String
    public var entryPrice: Double
    public var sizePct: Double
    public var openedAt: String
    public var exitBy: String
    public var direction: String?
    public var markPrice: Double?
    public var markSource: String?
    public var markDate: String?
    public var unrealizedRet: Double?
    public var stopLoss: Double?
    public var takeProfit: Double?
    public var distToSl: Double?
    public var distToTp: Double?
    public var slAdvisory: Bool?
    public var hedgeTicker: String?
    public var thesis: String?
    public var killCriteria: [String]
    public var failureFactors: [String]
    public var mitigations: [String]
}

public struct History: Codable, Sendable, Equatable {
    public var trades: [ClosedTrade]
    public var equityCurve: [EquityPoint]
    public var winRate: Double?
    public var expectancy: Double?
    public var sharpe: Double?
    public var calibration: [CalibrationPoint]
    /// Phase 8 attribution is built in parallel; until then the server sends null + "pending_phase_8".
    public var attribution: [String: Double]?
    public var attributionStatus: String?
}

public struct ClosedTrade: Codable, Sendable, Equatable, Identifiable {
    public var id: Int
    public var ticker: String
    public var openedAt: String
    public var exitBy: String
    public var closedAt: String?
    public var entryPrice: Double
    public var closePrice: Double?
    public var sizePct: Double
    public var realizedRet: Double
    public var bookRet: Double
    public var predicted: Double?
    public var win: Bool
}

public struct EquityPoint: Codable, Sendable, Equatable, Identifiable {
    public var date: String
    public var equity: Double
    public var id: String { date }
}

public struct CalibrationPoint: Codable, Sendable, Equatable, Identifiable {
    public var ticker: String
    public var predicted: Double
    public var realized: Double
    public var id: String { "\(ticker)-\(predicted)-\(realized)" }
}

public struct PlaybookResponse: Codable, Sendable, Equatable {
    public var playbooks: [Playbook]
    public var kbCounts: [KBCount]
}

public struct Playbook: Codable, Sendable, Equatable, Identifiable {
    public var id: Int
    public var scenarioType: String
    public var scenario: String
    public var confidence: Double?
    public var strategyText: String?
    public var n: Int?
    public var medianMove: Double?
    public var baseRate: [BaseRate]
    public var whatToWatch: [String]
}

public struct BaseRate: Codable, Sendable, Equatable {
    public var label: String
    public var rate: Double
}

public struct KBCount: Codable, Sendable, Equatable {
    public var kind: String
    public var count: Int
}

public struct DecisionSummary: Codable, Sendable, Equatable, Identifiable {
    public var id: Int
    public var status: String
    public var submittedAt: String
    public var resolvedAt: String?
    public var positionId: Int?
    public var ticker: String?
    public var entry: Double?
    public var sizePct: Double?
    public var exitBy: String?
    public var direction: String?
}

/// GET /decisions/{id}: the summary fields + the review snapshot (null for pre-Phase-9 submissions).
public struct Dossier: Codable, Sendable, Equatable {
    public var id: Int
    public var status: String
    public var submittedAt: String
    public var positionId: Int?
    public var ticker: String?
    public var entry: Double?
    public var sizePct: Double?
    public var exitBy: String?
    public var direction: String?
    public var review: Review?
}

public struct Review: Codable, Sendable, Equatable {
    public var catalyst: ReviewCatalyst?
    public var dossier: StrategyDossier?
    public var dd: DiligenceDossier?
    public var decision: MDDecision?
}

public struct ReviewCatalyst: Codable, Sendable, Equatable {
    public var ticker: String?
    public var catalystType: String?
    public var eventDate: String?
}

public struct StrategyDossier: Codable, Sendable, Equatable {
    public var verdictSummary: String?
    public var killCriteria: [String]?
    public var preMortem: [String]?
    public var positionMemo: String?
    public var dissentLog: [String]?
    public var allEvidenceRefs: [String]?
    public var trade: TradeProposal?
}

public struct TradeProposal: Codable, Sendable, Equatable {
    public var targetLong: String?
    public var entry: Double?
    public var sizePct: Double?
    public var stopLoss: Double?
    public var takeProfit: Double?
    public var expectedReturnPct: Double?
    public var slAdvisory: Bool?
    public var exitByDate: String?
    public var holdsThroughCatalyst: Bool?
    public var pairRationale: String?
    public var hedge: HedgeRef?
}

public struct HedgeRef: Codable, Sendable, Equatable {
    public var ticker: String?
}

public struct DiligenceDossier: Codable, Sendable, Equatable {
    public var verdict: String?
    public var redFlags: [String]?
    public var strongestDisconfirmingEvidence: String?
    public var residualRisks: [String]?
    public var allEvidenceRefs: [String]?
}

public struct MDDecision: Codable, Sendable, Equatable {
    public var decision: String?
    public var rationale: String?
    public var acceptedResiduals: [String]?
    public var dissentPreserved: [String]?
    public var rounds: Int?
}

public struct GateResult: Codable, Sendable, Equatable {
    public var id: Int
    public var status: String
    public var positionId: Int?
}

public enum DashboardJSON {
    public static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }
}
