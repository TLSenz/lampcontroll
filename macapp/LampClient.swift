import CryptoKit
import Foundation

struct LampState {
    var isOn: Bool
    var rgb: Int
    var luminance: Int
    var model: String
    var firmware: String
}

enum LampError: LocalizedError {
    case badURL
    case http(Int)
    case badResponse(String)
    case deviceError(String)

    var errorDescription: String? {
        switch self {
        case .badURL:
            return "Invalid lamp address."
        case .http(let code):
            return "The lamp returned HTTP \(code)."
        case .badResponse(let message):
            return "Unexpected lamp response: \(message)"
        case .deviceError(let message):
            return "Lamp error: \(message)"
        }
    }
}

struct LampClient {
    var host: String
    var port: Int = 80
    var key: String = ""

    private func packet(namespace: String, method: String, payload: [String: Any]) -> [String: Any] {
        let messageId = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        let timestamp = Int(Date().timeIntervalSince1970)
        let material = messageId + key + String(timestamp)
        let digest = Insecure.MD5.hash(data: Data(material.utf8))
        let sign = digest.map { String(format: "%02x", $0) }.joined()
        return [
            "header": [
                "messageId": messageId,
                "namespace": namespace,
                "method": method,
                "payloadVersion": 1,
                "from": "LampControll",
                "timestamp": timestamp,
                "timestampMs": 0,
                "sign": sign,
            ],
            "payload": payload,
        ]
    }

    func send(namespace: String, method: String, payload: [String: Any]) async throws -> [String: Any] {
        guard let url = URL(string: "http://\(host):\(port)/config") else {
            throw LampError.badURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 5
        request.setValue("application/json; charset=UTF-8", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(
            withJSONObject: packet(namespace: namespace, method: method, payload: payload)
        )

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw LampError.badResponse("no HTTP response")
        }
        guard http.statusCode == 200 else {
            throw LampError.http(http.statusCode)
        }
        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw LampError.badResponse("body is not JSON")
        }
        if let header = json["header"] as? [String: Any],
           (header["method"] as? String) == "ERROR" {
            let payload = json["payload"] as? [String: Any] ?? [:]
            let error = payload["error"] as? [String: Any] ?? [:]
            let detail = error["detail"] as? String ?? "unknown error"
            throw LampError.deviceError(detail)
        }
        return json
    }

    func fetchState() async throws -> LampState {
        let json = try await send(
            namespace: "Appliance.System.All",
            method: "GET",
            payload: ["all": [:]]
        )
        guard let payload = json["payload"] as? [String: Any],
              let all = payload["all"] as? [String: Any],
              let system = all["system"] as? [String: Any],
              let digest = all["digest"] as? [String: Any] else {
            throw LampError.badResponse("missing system/digest")
        }
        let togglex = digest["togglex"] as? [[String: Any]] ?? []
        let light = digest["light"] as? [String: Any] ?? [:]
        let hardware = system["hardware"] as? [String: Any] ?? [:]
        let firmware = system["firmware"] as? [String: Any] ?? [:]
        let onoff = togglex.first?["onoff"] as? Int ?? light["onoff"] as? Int ?? 0
        return LampState(
            isOn: onoff == 1,
            rgb: light["rgb"] as? Int ?? 0xFFFFFF,
            luminance: light["luminance"] as? Int ?? 100,
            model: hardware["type"] as? String ?? "Meross lamp",
            firmware: firmware["version"] as? String ?? "?"
        )
    }

    func setPower(_ on: Bool) async throws {
        _ = try await send(
            namespace: "Appliance.Control.ToggleX",
            method: "SET",
            payload: ["togglex": ["channel": 0, "onoff": on ? 1 : 0]]
        )
    }

    func setLight(rgb: Int, luminance: Int) async throws {
        _ = try await send(
            namespace: "Appliance.Control.Light",
            method: "SET",
            payload: [
                "light": [
                    "channel": 0,
                    "rgb": rgb,
                    "luminance": max(0, min(100, luminance)),
                    "capacity": 7,
                ]
            ]
        )
    }
}
