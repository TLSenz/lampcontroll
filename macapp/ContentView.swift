import SwiftUI

@MainActor
final class LampModel: ObservableObject {
    @Published var isOn = false
    @Published var brightness: Double = 100
    @Published var rgb: Int = 0x0000FF
    @Published var host: String
    @Published var status = "Connecting…"
    @Published var connected = false
    @Published var busy = false

    private let defaults = UserDefaults.standard
    private let hostKey = "lampHost"

    init() {
        host = defaults.string(forKey: hostKey) ?? "192.168.1.111"
        Task { await refresh() }
    }

    private var client: LampClient {
        LampClient(host: host.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    func refresh() async {
        busy = true
        defer { busy = false }
        do {
            let state = try await client.fetchState()
            apply(state)
            connected = true
            status = "\(state.model) · fw \(state.firmware)"
        } catch {
            connected = false
            status = shortError(error)
        }
    }

    func setPower(_ on: Bool) async {
        busy = true
        defer { busy = false }
        do {
            try await client.setPower(on)
            try await Task.sleep(nanoseconds: 500_000_000)
            try await reload()
            connected = true
            status = on ? "Lamp on" : "Lamp off"
        } catch {
            connected = false
            status = shortError(error)
        }
    }

    func applyBrightness() async {
        busy = true
        defer { busy = false }
        do {
            try await client.setLight(rgb: rgb, luminance: Int(brightness))
            try await Task.sleep(nanoseconds: 500_000_000)
            try await reload()
            connected = true
            status = "Brightness \(Int(brightness))%"
        } catch {
            connected = false
            status = shortError(error)
        }
    }

    func setColor(_ value: Int) async {
        busy = true
        defer { busy = false }
        do {
            if !isOn {
                try await client.setPower(true)
                try await Task.sleep(nanoseconds: 400_000_000)
            }
            try await client.setLight(rgb: value, luminance: Int(brightness))
            try await Task.sleep(nanoseconds: 500_000_000)
            try await reload()
            connected = true
            status = "Colour applied"
        } catch {
            connected = false
            status = shortError(error)
        }
    }

    func saveHostAndRefresh() async {
        defaults.set(host, forKey: hostKey)
        await refresh()
    }

    private func reload() async throws {
        let state = try await client.fetchState()
        apply(state)
    }

    private func apply(_ state: LampState) {
        isOn = state.isOn
        brightness = Double(state.luminance)
        rgb = state.rgb
    }

    private func shortError(_ error: Error) -> String {
        let message = error.localizedDescription
        return message.count > 90 ? String(message.prefix(90)) + "…" : message
    }
}

private struct ColorPreset: Identifiable {
    let id = UUID()
    let name: String
    let value: Int
}

private let presets: [ColorPreset] = [
    .init(name: "White", value: 0xFFFFFF),
    .init(name: "Warm", value: 0xFFB46B),
    .init(name: "Red", value: 0xFF3B30),
    .init(name: "Green", value: 0x34C759),
    .init(name: "Blue", value: 0x007AFF),
    .init(name: "Purple", value: 0xAF52DE),
    .init(name: "Orange", value: 0xFF9500),
]

struct ContentView: View {
    @StateObject private var model = LampModel()

    private var lampColor: Color { Color(hex: model.rgb) }

    var body: some View {
        VStack(spacing: 20) {
            header
            powerCard
            brightnessCard
            colourCard
            footer
        }
        .padding(24)
        .frame(width: 380)
        .background(
            LinearGradient(
                colors: [
                    Color(nsColor: .windowBackgroundColor),
                    lampColor.opacity(model.isOn ? 0.10 : 0.03),
                ],
                startPoint: .top,
                endPoint: .bottom
            )
        )
    }

    private var header: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(lampColor.opacity(model.isOn ? 1 : 0.25))
                    .frame(width: 42, height: 42)
                Image(systemName: "lightbulb.fill")
                    .font(.system(size: 19, weight: .semibold))
                    .foregroundStyle(model.isOn ? .white : .secondary)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text("LampControll")
                    .font(.system(size: 18, weight: .semibold, design: .rounded))
                HStack(spacing: 5) {
                    Circle()
                        .fill(model.connected ? Color.green : Color.orange)
                        .frame(width: 7, height: 7)
                    Text(model.status)
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer()
            if model.busy {
                ProgressView()
                    .controlSize(.small)
            } else {
                Button {
                    Task { await model.refresh() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 14, weight: .semibold))
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .help("Refresh")
            }
        }
    }

    private var powerCard: some View {
        HStack(spacing: 16) {
            Button {
                Task { await model.setPower(!model.isOn) }
            } label: {
                ZStack {
                    Circle()
                        .fill(model.isOn ? lampColor : Color.secondary.opacity(0.18))
                        .frame(width: 74, height: 74)
                        .shadow(
                            color: model.isOn ? lampColor.opacity(0.45) : .clear,
                            radius: 18
                        )
                    Image(systemName: "power")
                        .font(.system(size: 28, weight: .semibold))
                        .foregroundStyle(model.isOn ? .white : .secondary)
                }
            }
            .buttonStyle(.plain)
            .help(model.isOn ? "Turn off" : "Turn on")

            VStack(alignment: .leading, spacing: 4) {
                Text(model.isOn ? "On" : "Off")
                    .font(.system(size: 26, weight: .bold, design: .rounded))
                Text(model.isOn ? "Tap to switch off" : "Tap to switch on")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(16)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    private var brightnessCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("Brightness", systemImage: "sun.max.fill")
                    .font(.system(size: 13, weight: .medium))
                Spacer()
                Text("\(Int(model.brightness))%")
                    .font(.system(size: 13, weight: .semibold, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            Slider(
                value: $model.brightness,
                in: 0...100,
                step: 1,
                onEditingChanged: { editing in
                    if !editing {
                        Task { await model.applyBrightness() }
                    }
                }
            )
            .tint(lampColor)
        }
        .padding(16)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    private var colourCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Colour", systemImage: "paintpalette.fill")
                .font(.system(size: 13, weight: .medium))
            HStack(spacing: 10) {
                ForEach(presets) { preset in
                    Button {
                        Task { await model.setColor(preset.value) }
                    } label: {
                        Circle()
                            .fill(Color(hex: preset.value))
                            .frame(width: 30, height: 30)
                            .overlay(
                                Circle()
                                    .strokeBorder(
                                        model.rgb == preset.value ? Color.primary.opacity(0.8) : Color.white.opacity(0.25),
                                        lineWidth: model.rgb == preset.value ? 2 : 1
                                    )
                            )
                    }
                    .buttonStyle(.plain)
                    .help(preset.name)
                }
            }
        }
        .padding(16)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    private var footer: some View {
        HStack(spacing: 8) {
            Image(systemName: "wifi")
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
            TextField("Lamp IP", text: $model.host)
                .textFieldStyle(.plain)
                .font(.system(size: 12, design: .monospaced))
                .onSubmit {
                    Task { await model.saveHostAndRefresh() }
                }
            Button("Connect") {
                Task { await model.saveHostAndRefresh() }
            }
            .font(.system(size: 12, weight: .medium))
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 4)
    }
}

extension Color {
    init(hex: Int) {
        let red = Double((hex >> 16) & 0xFF) / 255.0
        let green = Double((hex >> 8) & 0xFF) / 255.0
        let blue = Double(hex & 0xFF) / 255.0
        self.init(red: red, green: green, blue: blue)
    }
}
