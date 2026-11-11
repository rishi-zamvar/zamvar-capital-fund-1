import Foundation
import Observation

public enum LoadState<T: Sendable & Equatable>: Equatable, Sendable {
    case idle, loading, loaded(T), failed(String), unauthorized

    public var value: T? { if case .loaded(let v) = self { v } else { nil } }
}

func message(_ error: Error) -> String { (error as? LocalizedError)?.errorDescription ?? error.localizedDescription }

func state<T>(for error: Error) -> LoadState<T> {
    error as? APIError == .unauthorized ? .unauthorized : .failed(message(error))
}

/// One read-only screen's data (This Week / History / Playbook / a dossier).
@MainActor @Observable public final class Loader<T: Sendable & Equatable> {
    public private(set) var state: LoadState<T> = .idle
    private let fetch: @Sendable () async throws -> T

    public init(_ fetch: @escaping @Sendable () async throws -> T) { self.fetch = fetch }

    public func load() async {
        if state.value == nil { state = .loading }
        do { state = .loaded(try await fetch()) } catch { state = Fund1Kit.state(for: error) }
    }
}

/// Pending decisions + the gate. approve / reject are ONLY called from an explicit, confirmed tap.
@MainActor @Observable public final class ApprovalsViewModel {
    public private(set) var state: LoadState<[DecisionSummary]> = .idle
    public var actionError: String?
    public let client: any DashboardClient

    public init(client: any DashboardClient) { self.client = client }

    public func load() async {
        if state.value == nil { state = .loading }
        do { state = .loaded(try await client.decisions()) } catch { state = Fund1Kit.state(for: error) }
    }

    @discardableResult public func approve(id: Int) async -> Bool { await gate { try await client.approve(id: id) } }
    @discardableResult public func reject(id: Int) async -> Bool { await gate { try await client.reject(id: id) } }

    private func gate(_ call: () async throws -> GateResult) async -> Bool {
        actionError = nil
        do { _ = try await call() } catch { actionError = message(error); return false }
        await load()
        return true
    }
}

public struct ChatMessage: Identifiable, Equatable, Sendable {
    public let id = UUID()
    public var text: String
    public let fromUser: Bool
    public var isError = false
}

@MainActor @Observable public final class ChatViewModel {
    public private(set) var messages: [ChatMessage] = []
    public private(set) var isStreaming = false
    public var draft = ""
    private let client: any DashboardClient

    public init(client: any DashboardClient) { self.client = client }

    public func send() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isStreaming else { return }
        draft = ""
        messages.append(ChatMessage(text: text, fromUser: true))
        messages.append(ChatMessage(text: "", fromUser: false))
        let i = messages.count - 1
        isStreaming = true
        defer { isStreaming = false }
        do {
            for try await ev in client.chat(text) {
                switch ev.event {
                case "delta": messages[i].text += ev.field("text") ?? ""
                case "error": messages[i].text = ev.field("message") ?? "chat failed"; messages[i].isError = true
                default: break
                }
            }
        } catch {
            messages[i].text = message(error)
            messages[i].isError = true
        }
    }
}
