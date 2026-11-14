package com.thalium.lampcontroll;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.UUID;

/**
 * Minimal Meross local-protocol client for the MSL120DR lamp.
 * No cloud, no Meross account, no external dependencies.
 */
public final class LampClient {
    public static final String DEFAULT_HOST = "192.168.1.111";
    private static final int PORT = 80;
    private static final String KEY = "";

    public static final class State {
        public final boolean isOn;
        public final int rgb;
        public final int luminance;
        public final String model;
        public final String firmware;

        State(boolean isOn, int rgb, int luminance, String model, String firmware) {
            this.isOn = isOn;
            this.rgb = rgb;
            this.luminance = luminance;
            this.model = model;
            this.firmware = firmware;
        }
    }

    private JSONObject send(String host, String namespace, String method, JSONObject payload)
            throws Exception {
        String messageId = UUID.randomUUID().toString().replace("-", "");
        long timestamp = System.currentTimeMillis() / 1000L;
        String sign = md5(messageId + KEY + timestamp);

        JSONObject header = new JSONObject();
        header.put("messageId", messageId);
        header.put("namespace", namespace);
        header.put("method", method);
        header.put("payloadVersion", 1);
        header.put("from", "LampControllAndroid");
        header.put("timestamp", timestamp);
        header.put("timestampMs", 0);
        header.put("sign", sign);

        JSONObject root = new JSONObject();
        root.put("header", header);
        root.put("payload", payload);

        HttpURLConnection connection = null;
        try {
            URL url = new URL("http://" + host.trim() + ":" + PORT + "/config");
            connection = (HttpURLConnection) url.openConnection();
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(5000);
            connection.setReadTimeout(5000);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json; charset=UTF-8");

            byte[] bytes = root.toString().getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(bytes.length);
            try (OutputStream out = connection.getOutputStream()) {
                out.write(bytes);
            }

            int code = connection.getResponseCode();
            InputStream stream = code >= 400 ? connection.getErrorStream() : connection.getInputStream();
            String body = readAll(stream);
            if (code != 200) {
                throw new IOException("HTTP " + code + (body.isEmpty() ? "" : ": " + body));
            }
            JSONObject json = new JSONObject(body);
            JSONObject responseHeader = json.optJSONObject("header");
            if (responseHeader != null && "ERROR".equals(responseHeader.optString("method"))) {
                JSONObject error = json.optJSONObject("payload") != null
                        ? json.optJSONObject("payload").optJSONObject("error")
                        : null;
                throw new IOException("Lamp error: "
                        + (error != null ? error.optString("detail", "unknown") : "unknown"));
            }
            return json;
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    public State fetchState(String host) throws Exception {
        JSONObject json = send(host, "Appliance.System.All", "GET",
                new JSONObject().put("all", new JSONObject()));
        JSONObject all = json.getJSONObject("payload").getJSONObject("all");
        JSONObject system = all.getJSONObject("system");
        JSONObject digest = all.getJSONObject("digest");
        JSONObject light = digest.optJSONObject("light");

        int onoff = 0;
        JSONArray togglex = digest.optJSONArray("togglex");
        if (togglex != null && togglex.length() > 0) {
            onoff = togglex.getJSONObject(0).optInt("onoff", 0);
        } else if (light != null) {
            onoff = light.optInt("onoff", 0);
        }

        String model = system.optJSONObject("hardware") != null
                ? system.optJSONObject("hardware").optString("type", "Meross lamp")
                : "Meross lamp";
        String firmware = system.optJSONObject("firmware") != null
                ? system.optJSONObject("firmware").optString("version", "?")
                : "?";

        return new State(
                onoff == 1,
                light != null ? light.optInt("rgb", 0xFFFFFF) : 0xFFFFFF,
                light != null ? light.optInt("luminance", 100) : 100,
                model,
                firmware
        );
    }

    public void setPower(String host, boolean on) throws Exception {
        JSONObject toggle = new JSONObject();
        toggle.put("channel", 0);
        toggle.put("onoff", on ? 1 : 0);
        send(host, "Appliance.Control.ToggleX", "SET",
                new JSONObject().put("togglex", toggle));
    }

    public void setLight(String host, int rgb, int luminance) throws Exception {
        JSONObject light = new JSONObject();
        light.put("channel", 0);
        light.put("rgb", rgb & 0xFFFFFF);
        light.put("luminance", Math.max(0, Math.min(100, luminance)));
        light.put("capacity", 7);
        send(host, "Appliance.Control.Light", "SET",
                new JSONObject().put("light", light));
    }

    private static String readAll(InputStream stream) throws IOException {
        if (stream == null) {
            return "";
        }
        StringBuilder builder = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                builder.append(line);
            }
        }
        return builder.toString();
    }

    private static String md5(String value) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("MD5");
        byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
        StringBuilder builder = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            builder.append(String.format("%02x", b & 0xff));
        }
        return builder.toString();
    }
}
