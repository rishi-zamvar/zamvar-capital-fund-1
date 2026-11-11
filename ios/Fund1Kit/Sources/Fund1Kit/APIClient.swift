import Foundation

public enum APIError: Error, Equatable, Sendable, LocalizedError {
    case unauthorized
    case server(String)

    public var errorDescription: String? {
        switch self {
        case .unauthorized: "Unauthorized — check the server token in Settings."
        case .server(let m): m
        }
    }
}

/// Everything the app can ask the dashboard shim. The only writes are approve / reject.
public protocol DashboardClient: Sendable {
    func week() async throws -> Week
    func history() async throws -> History
    func playbook() async throws -> PlaybookResponse
    func decisions() async throws -> [DecisionSummary]
    func dossier(id: Int) async throws -> Dossier
    func approve(id: Int) async throws -> GateResult
    func reject(id: Int) async throws -> GateResult
    func chat(_ message: String) -> AsyncThrowingStream<SSEEvent, Error>
}

public struct APIClient: DashboardClient {
    public let baseURL: URL
    let token: String
    let session: URLSession

    public init(baseURL: URL, token: String, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.token = token
        self.session = session
    }

    func request(_ path: String, method: String = "GET", body: Data? = nil) -> URLRequest {
        var r = URLRequest(url: baseURL.appending(path: "api/v1/" + path))
        r.httpMethod = method
        r.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if let body {
            r.httpBody = body
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        r.timeoutInterval = 30
        return r
    }

    static func check(_ response: URLResponse, _ body: Data) throws {
        guard let http = response as? HTTPURLResponse else { throw APIError.server("no HTTP response") }
        if http.statusCode == 401 { throw APIError.unauthorized }
        guard (200..<300).contains(http.statusCode) else {
            let detail = (try? JSONSerialization.jsonObject(with: body) as? [String: Any])?["detail"] as? String
            throw APIError.server(detail ?? "server error \(http.statusCode)")
        }
    }

    func get<T: Decodable>(_ path: String, method: String = "GET") async throws -> T {
        let (data, resp) = try await session.data(for: request(path, method: method))
        try Self.check(resp, data)
        return try DashboardJSON.decoder().decode(T.self, from: data)
    }

    public func week() async throws -> Week { try await get("week") }
    public func history() async throws -> History { try await get("history") }
    public func playbook() async throws -> PlaybookResponse { try await get("playbook") }
    public func decisions() async throws -> [DecisionSummary] { try await get("decisions") }
    public func dossier(id: Int) async throws -> Dossier { try await get("decisions/\(id)") }
    public func approve(id: Int) async throws -> GateResult { try await get("decisions/\(id)/approve", method: "POST") }
    public func reject(id: Int) async throws -> GateResult { try await get("decisions/\(id)/reject", method: "POST") }

    public func chat(_ message: String) -> AsyncThrowingStream<SSEEvent, Error> {
        let req = request("chat", method: "POST", body: try? JSONEncoder().encode(["message": message]))
        let session = session
        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let (bytes, resp) = try await session.bytes(for: req)
                    if let http = resp as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                        var body = Data()
                        for try await b in bytes { body.append(b) }
                        try Self.check(resp, body)
                    }
                    var parser = SSEParser()
                    for try await line in bytes.lines {
                        if let ev = parser.feed(line) { continuation.yield(ev) }
                    }
                    if let ev = parser.finish() { continuation.yield(ev) }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}
