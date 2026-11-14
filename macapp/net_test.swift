import CryptoKit
import Foundation

let host = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "192.168.1.111"
let messageId = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
let timestamp = Int(Date().timeIntervalSince1970)
let sign = Insecure.MD5.hash(data: Data((messageId + "" + String(timestamp)).utf8))
    .map { String(format: "%02x", $0) }.joined()
let body: [String: Any] = [
    "header": [
        "messageId": messageId,
        "namespace": "Appliance.System.All",
        "method": "GET",
        "payloadVersion": 1,
        "from": "LampControllTest",
        "timestamp": timestamp,
        "timestampMs": 0,
        "sign": sign,
    ],
    "payload": ["all": [:]],
]
var request = URLRequest(url: URL(string: "http://\(host)/config")!)
request.httpMethod = "POST"
request.setValue("application/json", forHTTPHeaderField: "Content-Type")
request.httpBody = try JSONSerialization.data(withJSONObject: body)
request.timeoutInterval = 5

let semaphore = DispatchSemaphore(value: 0)
URLSession.shared.dataTask(with: request) { data, response, error in
    print("error: \(String(describing: error))")
    if let http = response as? HTTPURLResponse {
        print("status: \(http.statusCode)")
    }
    if let data = data {
        print("body: \(String(data: data, encoding: .utf8) ?? "<non-utf8>")")
    }
    semaphore.signal()
}.resume()
semaphore.wait()
