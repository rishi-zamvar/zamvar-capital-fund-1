import Testing
@testable import Fund1Kit

@Suite struct SSEParserTests {
    func parse(_ lines: [String]) -> [SSEEvent] {
        var p = SSEParser()
        var out = lines.compactMap { p.feed($0) }
        if let last = p.finish() { out.append(last) }
        return out
    }

    @Test func blankLineDispatchesAndMultilineDataJoins() {
        let ev = parse(["event: delta", "data: a", "data: b", "", ": keep-alive"])
        #expect(ev == [SSEEvent(event: "delta", data: "a\nb")])
    }

    @Test func newEventLineDispatchesWhenBlankLinesAreDropped() {
        let ev = parse(["event: delta", #"data: {"text":"hi"}"#, "event: done", "data: {}"])
        #expect(ev.map(\.event) == ["delta", "done"])
        #expect(ev[0].field("text") == "hi")
    }
}
