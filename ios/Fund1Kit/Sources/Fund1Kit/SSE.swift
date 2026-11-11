import Foundation

public struct SSEEvent: Sendable, Equatable {
    public var event: String
    public var data: String

    public init(event: String, data: String) {
        self.event = event
        self.data = data
    }

    /// The `text` / `message` field of a JSON data payload (delta / error events), if any.
    public func field(_ key: String) -> String? {
        guard let obj = try? JSONSerialization.jsonObject(with: Data(data.utf8)) as? [String: Any] else { return nil }
        return obj[key] as? String
    }
}

/// Minimal text/event-stream parser. Feed it lines; a blank line dispatches the pending event.
/// `URLSession.AsyncBytes.lines` drops blank lines, so a new `event:` line after pending data also
/// dispatches, and `finish()` flushes whatever is left at end of stream.
public struct SSEParser: Sendable {
    private var event = "message"
    private var data: [String] = []
    private var hasField = false

    public init() {}

    public mutating func feed(_ line: String) -> SSEEvent? {
        if line.isEmpty { return dispatch() }
        if line.hasPrefix(":") { return nil }  // comment / keep-alive
        let (name, value) = Self.split(line)
        var out: SSEEvent?
        if name == "event" {
            if hasField { out = dispatch() }
            event = value
            hasField = true
        } else if name == "data" {
            data.append(value)
            hasField = true
        }
        return out
    }

    public mutating func finish() -> SSEEvent? { dispatch() }

    private mutating func dispatch() -> SSEEvent? {
        defer { event = "message"; data = []; hasField = false }
        guard hasField, !data.isEmpty else { return nil }
        return SSEEvent(event: event, data: data.joined(separator: "\n"))
    }

    private static func split(_ line: String) -> (String, String) {
        guard let colon = line.firstIndex(of: ":") else { return (line, "") }
        var value = line[line.index(after: colon)...]
        if value.hasPrefix(" ") { value = value.dropFirst() }
        return (String(line[..<colon]), String(value))
    }
}
