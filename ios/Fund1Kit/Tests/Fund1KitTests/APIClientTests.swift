import Foundation
import Testing
@testable import Fund1Kit

/// Canned responses keyed by path; records the last request.
final class StubProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var responses: [String: (Int, Data)] = [:]
    nonisolated(unsafe) static var lastRequest: URLRequest?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.lastRequest = request
        let (code, body) = Self.responses[request.url!.path] ?? (404, Data(#"{"detail":"missing"}"#.utf8))
        let resp = HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: nil,
                                   headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct APIClientTests {
    let client: APIClient = {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubProtocol.self]
        return APIClient(baseURL: URL(string: "http://100.64.0.1:8820")!, token: "t0ken-t0ken-t0ken",
                         session: URLSession(configuration: cfg))
    }()

    @Test func sendsBearerAndDecodes() async throws {
        StubProtocol.responses = ["/api/v1/week": (200, try fixture("week"))]
        let w = try await client.week()
        #expect(w.positions.count == 1)
        #expect(StubProtocol.lastRequest?.value(forHTTPHeaderField: "Authorization") == "Bearer t0ken-t0ken-t0ken")
    }

    @Test func maps401ToUnauthorized() async {
        StubProtocol.responses = ["/api/v1/week": (401, Data(#"{"detail":"unauthorized"}"#.utf8))]
        await #expect(throws: APIError.unauthorized) { try await client.week() }
    }

    @Test func mapsConflictToServerDetail() async {
        StubProtocol.responses = ["/api/v1/decisions/2/approve": (409, Data(#"{"detail":"decision 2 was rejected"}"#.utf8))]
        await #expect(throws: APIError.server("decision 2 was rejected")) { try await client.approve(id: 2) }
        #expect(StubProtocol.lastRequest?.httpMethod == "POST")
    }
}
