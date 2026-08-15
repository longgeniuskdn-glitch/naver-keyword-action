import Foundation

let fm = FileManager.default
let base = fm.homeDirectoryForCurrentUser.appendingPathComponent(".ai-code-usage", isDirectory: true)
try? fm.createDirectory(at: base, withIntermediateDirectories: true)
let logURL = base.appendingPathComponent("claude-statusline.log")
let usageURL = base.appendingPathComponent("claude-usage.json")

func appendLog(_ text: String) {
    let stamp = ISO8601DateFormatter().string(from: Date())
    let line = "[\(stamp)] \(text)\n"
    let data = line.data(using: .utf8)!
    if fm.fileExists(atPath: logURL.path), let h = try? FileHandle(forWritingTo: logURL) {
        try? h.seekToEnd()
        try? h.write(contentsOf: data)
        try? h.close()
    } else {
        try? data.write(to: logURL, options: .atomic)
    }
}

func number(_ dict: [String: Any]?, _ key: String) -> Double? {
    guard let v = dict?[key] else { return nil }
    if let n = v as? NSNumber { return n.doubleValue }
    if let s = v as? String { return Double(s) }
    return nil
}

let input = FileHandle.standardInput.readDataToEndOfFile()
guard let root = try? JSONSerialization.jsonObject(with: input) as? [String: Any] else {
    appendLog("invoked invalid_json=true")
    print("CL --")
    exit(0)
}

let limits = root["rate_limits"] as? [String: Any]
let five = limits?["five_hour"] as? [String: Any]
let seven = limits?["seven_day"] as? [String: Any]
let fiveUsed = number(five, "used_percentage")
let fiveReset = number(five, "resets_at")
let sevenUsed = number(seven, "used_percentage")
let sevenReset = number(seven, "resets_at")

var snapshot: [String: Any] = [
    "updatedAt": Int(Date().timeIntervalSince1970 * 1000),
    "fiveHour": NSNull(),
    "sevenDay": NSNull()
]
if let used = fiveUsed {
    snapshot["fiveHour"] = ["usedPercent": used, "resetsAt": fiveReset ?? NSNull()] as [String: Any]
}
if let used = sevenUsed {
    snapshot["sevenDay"] = ["usedPercent": used, "resetsAt": sevenReset ?? NSNull()] as [String: Any]
}
if let out = try? JSONSerialization.data(withJSONObject: snapshot, options: [.prettyPrinted, .sortedKeys]) {
    try? out.write(to: usageURL, options: .atomic)
}

appendLog("invoked has_rate_limits=\(limits != nil) five=\(fiveUsed != nil) seven=\(sevenUsed != nil)")

var parts: [String] = []
if let v = fiveUsed { parts.append("5h \(Int(v.rounded()))%") }
if let v = sevenUsed { parts.append("7d \(Int(v.rounded()))%") }
if parts.isEmpty { print("CL --") }
else { print("CL " + parts.joined(separator: " · ")) }
