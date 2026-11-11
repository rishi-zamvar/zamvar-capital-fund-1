import Foundation
import Testing
@testable import Fund1Kit

func fixture(_ name: String) throws -> Data {
    let url = try #require(Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Fixtures"))
    return try Data(contentsOf: url)
}

func decode<T: Decodable>(_ type: T.Type, _ name: String) throws -> T {
    try DashboardJSON.decoder().decode(T.self, from: fixture(name))
}

@Suite struct DecodingTests {
    @Test func weekDecodesPositionWithReview() throws {
        let w = try decode(Week.self, "week")
        #expect(w.pendingCount == 1 && w.benchmarkWeekly == 0.01)
        let p = try #require(w.positions.first)
        #expect(p.ticker == "ABCD" && p.slAdvisory == true && p.hedgeTicker == "PEER")
        #expect(p.killCriteria == ["CRL on CMC"] && p.mitigations == ["gap -> size"])
    }

    @Test func emptyWeekKeepsNullMetricsNil() throws {
        let w = try decode(Week.self, "week_empty")
        #expect(w.expectedReturn == nil && w.sharpe == nil && w.positions.isEmpty)
    }

    @Test func historyDecodesCurveAndPendingAttribution() throws {
        let h = try decode(History.self, "history")
        #expect(h.trades.count == 3 && h.equityCurve.count == 4 && h.calibration.count == 3)
        #expect(h.attribution == nil && h.attributionStatus == "pending_phase_8")
        let e = try decode(History.self, "history_empty")
        #expect(e.winRate == nil && e.trades.isEmpty)
    }

    @Test func playbookBaseRateLabelsSurviveSnakeCaseDecoding() throws {
        let pb = try decode(PlaybookResponse.self, "playbook")
        #expect(pb.playbooks.map(\.id) == [3, 1])
        #expect(pb.playbooks[1].baseRate == [BaseRate(label: "approve", rate: 0.8), BaseRate(label: "crl", rate: 0.2)])
        #expect(pb.kbCounts.contains(KBCount(kind: "evidence_source", count: 1)))
    }

    @Test func decisionsDossierAndGateResultDecode() throws {
        #expect(try decode([DecisionSummary].self, "decisions").first?.ticker == "PEND")
        let d = try decode(Dossier.self, "dossier")
        #expect(d.review?.dossier?.trade?.hedge?.ticker == "PEER")
        #expect(d.review?.dd?.strongestDisconfirmingEvidence == "AdCom split")
        #expect(d.review?.decision?.dissentPreserved == ["bear: CMC"])
        #expect(try decode(GateResult.self, "approve").positionId == 5)
    }
}
