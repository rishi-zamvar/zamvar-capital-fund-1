import Foundation
import Testing
@testable import Fund1Kit

final class StubClient: DashboardClient, @unchecked Sendable {
    var calls: [String] = []
    var fail: APIError?
    var chatEvents: [SSEEvent] = []

    private func check(_ name: String) throws {
        calls.append(name)
        if let fail { throw fail }
    }
    func week() async throws -> Week { try check("week"); return try decode(Week.self, "week") }
    func history() async throws -> History { try check("history"); return try decode(History.self, "history") }
    func playbook() async throws -> PlaybookResponse { try check("playbook"); return try decode(PlaybookResponse.self, "playbook") }
    func decisions() async throws -> [DecisionSummary] { try check("decisions"); return try decode([DecisionSummary].self, "decisions") }
    func dossier(id: Int) async throws -> Dossier { try check("dossier \(id)"); return try decode(Dossier.self, "dossier") }
    func approve(id: Int) async throws -> GateResult { try check("approve \(id)"); return GateResult(id: id, status: "approved", positionId: 5) }
    func reject(id: Int) async throws -> GateResult { try check("reject \(id)"); return GateResult(id: id, status: "rejected", positionId: nil) }
    func chat(_ message: String) -> AsyncThrowingStream<SSEEvent, Error> {
        calls.append("chat")
        let events = chatEvents
        return AsyncThrowingStream { c in events.forEach { c.yield($0) }; c.finish() }
    }
}

@MainActor @Suite struct ViewModelTests {
    @Test func loaderGoesLoadedOrFailedOrUnauthorized() async {
        let stub = StubClient()
        let vm = Loader { try await stub.week() }
        await vm.load()
        #expect(vm.state.value?.pendingCount == 1)

        stub.fail = .server("boom")
        await vm.load()
        #expect(vm.state == .failed("boom"))

        stub.fail = .unauthorized
        await vm.load()
        #expect(vm.state == .unauthorized)
    }

    @Test func approvalsNeverCallTheGateOnLoad() async {
        let stub = StubClient()
        let vm = ApprovalsViewModel(client: stub)
        await vm.load()
        #expect(vm.state.value?.count == 1)
        #expect(!stub.calls.contains { $0.hasPrefix("approve") || $0.hasPrefix("reject") })
    }

    @Test func approveAndRejectCallGateThenReload() async {
        let stub = StubClient()
        let vm = ApprovalsViewModel(client: stub)
        #expect(await vm.approve(id: 2) == true)
        #expect(stub.calls == ["approve 2", "decisions"])
        stub.calls = []
        #expect(await vm.reject(id: 2) == true)
        #expect(stub.calls == ["reject 2", "decisions"])
    }

    @Test func gateFailureSurfacesMessage() async {
        let stub = StubClient()
        stub.fail = .server("decision 2 was rejected")
        let vm = ApprovalsViewModel(client: stub)
        #expect(await vm.approve(id: 2) == false)
        #expect(vm.actionError == "decision 2 was rejected")
    }

    @Test func chatStreamsDeltasIntoAssistantMessage() async {
        let stub = StubClient()
        stub.chatEvents = [SSEEvent(event: "delta", data: #"{"text":"Hel"}"#),
                           SSEEvent(event: "delta", data: #"{"text":"lo"}"#),
                           SSEEvent(event: "done", data: "{}")]
        let vm = ChatViewModel(client: stub)
        vm.draft = "why ABCD?"
        await vm.send()
        #expect(vm.messages.map(\.text) == ["why ABCD?", "Hello"])
        #expect(vm.messages.map(\.fromUser) == [true, false])
        #expect(vm.draft.isEmpty && !vm.isStreaming)
    }

    @Test func chatErrorEventSurfacesText() async {
        let stub = StubClient()
        stub.chatEvents = [SSEEvent(event: "error", data: #"{"message":"LLM down"}"#)]
        let vm = ChatViewModel(client: stub)
        vm.draft = "hi"
        await vm.send()
        #expect(vm.messages.last?.text == "LLM down" && vm.messages.last?.isError == true)
    }
}
