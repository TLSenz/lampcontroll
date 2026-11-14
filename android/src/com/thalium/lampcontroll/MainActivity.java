package com.thalium.lampcontroll;

import android.app.Activity;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int BG = Color.rgb(15, 23, 42);
    private static final int CARD = Color.rgb(30, 41, 59);
    private static final int FIELD = Color.rgb(15, 23, 42);
    private static final int TEXT = Color.rgb(226, 232, 240);
    private static final int MUTED = Color.rgb(148, 163, 184);
    private static final int ACCENT = Color.rgb(34, 197, 94);
    private static final int DANGER = Color.rgb(248, 113, 113);
    private static final int OFF_BUTTON = Color.rgb(51, 65, 85);

    private static final int[] PALETTE = {
            0xFFFFFF, 0xFFB46B, 0xFF3B30, 0x34C759, 0x007AFF, 0xAF52DE, 0xFF9500
    };

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private final LampClient client = new LampClient();

    private SharedPreferences prefs;
    private TextView statusView;
    private TextView brightnessLabel;
    private Button powerButton;
    private SeekBar brightnessBar;
    private EditText hostField;

    private String host = LampClient.DEFAULT_HOST;
    private boolean isOn = false;
    private int rgb = 0xFFFFFF;
    private int luminance = 100;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences("lampcontroll", MODE_PRIVATE);
        host = prefs.getString("host", LampClient.DEFAULT_HOST);

        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        setContentView(buildUi());
        refresh();
    }

    private View buildUi() {
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(BG);
        scroll.setFillViewport(true);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(28), dp(20), dp(28));
        scroll.addView(root, new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        TextView title = new TextView(this);
        title.setText("LampControll");
        title.setTextSize(28);
        title.setTextColor(TEXT);
        title.setTypeface(Typeface.create("sans-serif", Typeface.BOLD));
        root.addView(title);

        statusView = new TextView(this);
        statusView.setText("○ Connecting…");
        statusView.setTextSize(13);
        statusView.setTextColor(MUTED);
        statusView.setPadding(0, dp(4), 0, dp(4));
        root.addView(statusView);

        root.addView(buildPowerCard(), cardParams());
        root.addView(buildBrightnessCard(), cardParams());
        root.addView(buildColorCard(), cardParams());
        root.addView(buildConnectionCard(), cardParams());

        TextView footer = new TextView(this);
        footer.setText("Local Meross control · no cloud");
        footer.setTextSize(11);
        footer.setTextColor(MUTED);
        footer.setGravity(android.view.Gravity.CENTER);
        footer.setPadding(0, dp(20), 0, 0);
        root.addView(footer);

        return scroll;
    }

    private View buildPowerCard() {
        LinearLayout card = card();

        TextView label = new TextView(this);
        label.setText("Power");
        label.setTextSize(13);
        label.setTextColor(MUTED);
        label.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        card.addView(label);

        powerButton = new Button(this);
        powerButton.setText("Turn on");
        powerButton.setAllCaps(false);
        powerButton.setTextSize(20);
        powerButton.setTextColor(Color.WHITE);
        powerButton.setBackground(rounded(OFF_BUTTON, 16));
        powerButton.setOnClickListener(v -> setPower(!isOn));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(72));
        params.topMargin = dp(10);
        card.addView(powerButton, params);

        return card;
    }

    private View buildBrightnessCard() {
        LinearLayout card = card();

        brightnessLabel = new TextView(this);
        brightnessLabel.setText("Brightness 100%");
        brightnessLabel.setTextSize(13);
        brightnessLabel.setTextColor(MUTED);
        brightnessLabel.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        card.addView(brightnessLabel);

        brightnessBar = new SeekBar(this);
        brightnessBar.setMax(100);
        brightnessBar.setProgress(luminance);
        brightnessBar.setProgressTintList(ColorStateList.valueOf(ACCENT));
        brightnessBar.setThumbTintList(ColorStateList.valueOf(ACCENT));
        brightnessBar.setPadding(0, dp(8), 0, 0);
        brightnessBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) {
                brightnessLabel.setText("Brightness " + progress + "%");
            }

            @Override
            public void onStartTrackingTouch(SeekBar seekBar) {
            }

            @Override
            public void onStopTrackingTouch(SeekBar seekBar) {
                setBrightness(seekBar.getProgress());
            }
        });
        card.addView(brightnessBar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        return card;
    }

    private View buildColorCard() {
        LinearLayout card = card();

        TextView label = new TextView(this);
        label.setText("Colour");
        label.setTextSize(13);
        label.setTextColor(MUTED);
        label.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        card.addView(label);

        HorizontalScrollView scroller = new HorizontalScrollView(this);
        scroller.setHorizontalScrollBarEnabled(false);
        scroller.setPadding(0, dp(12), 0, 0);

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        for (int colour : PALETTE) {
            View swatch = new View(this);
            GradientDrawable shape = new GradientDrawable();
            shape.setShape(GradientDrawable.OVAL);
            shape.setColor(0xFF000000 | colour);
            shape.setStroke(dp(1), Color.argb(90, 255, 255, 255));
            swatch.setBackground(shape);
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(38), dp(38));
            params.rightMargin = dp(10);
            row.addView(swatch, params);
            swatch.setOnClickListener(v -> setColor(colour));
        }
        scroller.addView(row);
        card.addView(scroller);
        return card;
    }

    private View buildConnectionCard() {
        LinearLayout card = card();

        TextView label = new TextView(this);
        label.setText("Lamp address");
        label.setTextSize(13);
        label.setTextColor(MUTED);
        label.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        card.addView(label);

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(0, dp(10), 0, 0);

        hostField = new EditText(this);
        hostField.setText(host);
        hostField.setSingleLine(true);
        hostField.setTextSize(14);
        hostField.setTextColor(TEXT);
        hostField.setHintTextColor(MUTED);
        hostField.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        hostField.setBackground(rounded(FIELD, 10));
        hostField.setPadding(dp(12), dp(10), dp(12), dp(10));
        LinearLayout.LayoutParams hostParams = new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        row.addView(hostField, hostParams);

        Button connect = new Button(this);
        connect.setText("Connect");
        connect.setAllCaps(false);
        connect.setTextColor(Color.WHITE);
        connect.setBackground(rounded(ACCENT, 10));
        connect.setOnClickListener(v -> {
            String value = hostField.getText().toString().trim();
            host = value.isEmpty() ? LampClient.DEFAULT_HOST : value;
            prefs.edit().putString("host", host).apply();
            refresh();
        });
        LinearLayout.LayoutParams buttonParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        buttonParams.leftMargin = dp(8);
        row.addView(connect, buttonParams);

        card.addView(row);
        return card;
    }

    private void refresh() {
        setStatus("Connecting…", false);
        executor.execute(() -> {
            try {
                LampClient.State state = client.fetchState(host);
                main.post(() -> applyState(state));
            } catch (Exception error) {
                main.post(() -> showError(error));
            }
        });
    }

    private void applyState(LampClient.State state) {
        isOn = state.isOn;
        rgb = state.rgb;
        luminance = state.luminance;

        powerButton.setText(isOn ? "Turn off" : "Turn on");
        powerButton.setBackground(rounded(isOn ? ACCENT : OFF_BUTTON, 16));
        brightnessBar.setProgress(luminance);
        brightnessLabel.setText("Brightness " + luminance + "%");
        setStatus("● " + state.model + " · fw " + state.firmware
                + (isOn ? " · On" : " · Off"), true);
    }

    private void setPower(boolean on) {
        setStatus("Sending…", false);
        executor.execute(() -> {
            try {
                client.setPower(host, on);
                Thread.sleep(450);
                LampClient.State state = client.fetchState(host);
                main.post(() -> applyState(state));
            } catch (Exception error) {
                main.post(() -> showError(error));
            }
        });
    }

    private void setColor(int colour) {
        setStatus("Sending colour…", false);
        executor.execute(() -> {
            try {
                if (!isOn) {
                    client.setPower(host, true);
                    Thread.sleep(300);
                }
                client.setLight(host, colour, luminance);
                Thread.sleep(450);
                LampClient.State state = client.fetchState(host);
                main.post(() -> applyState(state));
            } catch (Exception error) {
                main.post(() -> showError(error));
            }
        });
    }

    private void setBrightness(int value) {
        setStatus("Sending brightness…", false);
        executor.execute(() -> {
            try {
                if (!isOn) {
                    client.setPower(host, true);
                    Thread.sleep(300);
                }
                client.setLight(host, rgb, value);
                Thread.sleep(450);
                LampClient.State state = client.fetchState(host);
                main.post(() -> applyState(state));
            } catch (Exception error) {
                main.post(() -> showError(error));
            }
        });
    }

    private void setStatus(String text, boolean connected) {
        statusView.setText(text);
        statusView.setTextColor(connected ? ACCENT : MUTED);
    }

    private void showError(Exception error) {
        String message = error.getMessage();
        if (message == null || message.isEmpty()) {
            message = error.getClass().getSimpleName();
        }
        setStatus("○ " + message, false);
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }

    private LinearLayout card() {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(16), dp(16), dp(16), dp(16));
        card.setBackground(rounded(CARD, 18));
        return card;
    }

    private LinearLayout.LayoutParams cardParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.topMargin = dp(14);
        return params;
    }

    private GradientDrawable rounded(int colour, float radiusDp) {
        GradientDrawable shape = new GradientDrawable();
        shape.setShape(GradientDrawable.RECTANGLE);
        shape.setColor(0xFF000000 | colour);
        shape.setCornerRadius(dp(radiusDp));
        return shape;
    }

    private int dp(float value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }
}
