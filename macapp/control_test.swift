import Foundation

@main
struct ControlTest {
    static func main() async {
        let client = LampClient(host: "192.168.1.111")
        do {
            let before = try await client.fetchState()
            print("before: on=\(before.isOn) rgb=#\(String(format: "%06x", before.rgb))")

            try await client.setPower(!before.isOn)
            try await Task.sleep(nanoseconds: 600_000_000)
            let afterToggle = try await client.fetchState()
            print("toggle: on=\(afterToggle.isOn) verified=\(afterToggle.isOn != before.isOn)")

            try await client.setPower(before.isOn)
            try await Task.sleep(nanoseconds: 400_000_000)
            try await client.setLight(rgb: 0x34C759, luminance: before.luminance)
            try await Task.sleep(nanoseconds: 600_000_000)
            let afterColor = try await client.fetchState()
            print("colour: rgb=#\(String(format: "%06x", afterColor.rgb)) verified=\(afterColor.rgb == 0x34C759)")

            try await client.setLight(rgb: before.rgb, luminance: before.luminance)
            try await Task.sleep(nanoseconds: 400_000_000)
            let restored = try await client.fetchState()
            print("restored: on=\(restored.isOn) rgb=#\(String(format: "%06x", restored.rgb))")
        } catch {
            print("error: \(error)")
            exit(1)
        }
    }
}
