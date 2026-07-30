package com.myvision.codexusage;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.browser.customtabs.CustomTabsIntent;

public final class MainActivity extends Activity {
    private static final String USAGE_URL = "https://chatgpt.com/codex/cloud/settings/analytics";
    private static final String CHROME = "com.android.chrome";
    private static final String BRAVE = "com.brave.browser";
    private boolean openedThisResume = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildUi());
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (!openedThisResume) {
            openedThisResume = true;
            getWindow().getDecorView().postDelayed(() -> openUsage(true), 180);
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        openedThisResume = false;
    }

    private View buildUi() {
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Color.rgb(243, 244, 246));
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(22), dp(30), dp(22), dp(30));
        scroll.addView(root);

        root.addView(text("Codex 사용량", 29, true));
        TextView description = text(
                "앱을 실행하면 공식 ChatGPT Codex 사용량 페이지가 바로 열립니다.\n" +
                "처음 한 번 ChatGPT에 로그인하면 이후에는 로그인 상태가 유지됩니다.", 16, false);
        description.setPadding(0, dp(12), 0, dp(24));
        root.addView(description);

        root.addView(button("Codex 사용량 열기", v -> openUsage(false)));
        root.addView(button("최신 화면으로 다시 열기", v -> openUsage(true)));

        TextView guide = text(
                "사용 방법\n\n" +
                "1. Chrome 또는 Brave에서 ChatGPT 로그인\n" +
                "2. 사용량 페이지가 자동으로 표시됨\n" +
                "3. 최신 값이 필요하면 ‘최신 화면으로 다시 열기’ 선택\n\n" +
                "이 앱은 Mac과 연결하지 않으며 주소 입력도 필요 없습니다.", 15, false);
        guide.setPadding(0, dp(26), 0, 0);
        root.addView(guide);

        TextView note = text(
                "참고: Android 보안 구조상 Chrome의 로그인 정보를 이용하면서 다른 앱이 페이지 숫자를 몰래 읽을 수는 없습니다. 따라서 모바일은 공식 사용량 화면을 즉시 여는 방식입니다.", 13, false);
        note.setPadding(0, dp(26), 0, 0);
        root.addView(note);
        return scroll;
    }

    private void openUsage(boolean forceRefresh) {
        String target = forceRefresh ? USAGE_URL + "?app_refresh=" + System.currentTimeMillis() : USAGE_URL;
        String browser = supportedBrowser();
        if (browser == null) {
            Toast.makeText(this, "Chrome 또는 Brave를 설치한 뒤 다시 실행하세요.", Toast.LENGTH_LONG).show();
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(target)));
            return;
        }
        CustomTabsIntent tabs = new CustomTabsIntent.Builder().setShowTitle(true).setUrlBarHidingEnabled(false).build();
        tabs.intent.setPackage(browser);
        tabs.intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            tabs.launchUrl(this, Uri.parse(target));
        } catch (Exception e) {
            Intent fallback = new Intent(Intent.ACTION_VIEW, Uri.parse(target));
            fallback.setPackage(browser);
            startActivity(fallback);
        }
    }

    private String supportedBrowser() {
        PackageManager pm = getPackageManager();
        try { pm.getPackageInfo(CHROME, 0); return CHROME; } catch (Exception ignored) { }
        try { pm.getPackageInfo(BRAVE, 0); return BRAVE; } catch (Exception ignored) { }
        return null;
    }

    private Button button(String label, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextSize(16);
        button.setAllCaps(false);
        button.setGravity(Gravity.CENTER);
        button.setOnClickListener(listener);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(54));
        params.setMargins(0, 0, 0, dp(12));
        button.setLayoutParams(params);
        return button;
    }

    private TextView text(String value, int size, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(Color.rgb(17, 24, 39));
        if (bold) view.setTypeface(null, android.graphics.Typeface.BOLD);
        view.setLineSpacing(0, 1.25f);
        return view;
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density);
    }
}
