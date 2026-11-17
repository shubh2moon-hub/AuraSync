package com.aura.phonesync;

import android.app.Activity;
import android.content.pm.ActivityInfo;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.view.Gravity;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.List;

/**
 * Interactive in-app live simulator to test and preview all wallpapers in
 * true Portrait and true Landscape modes with live GL shaders.
 */
public class PreviewActivity extends Activity implements SurfaceHolder.Callback {
    private Prefs prefs;
    private Library lib;
    private final GlRenderer renderer = new GlRenderer();
    private HandlerThread thread;
    private Handler gl;
    private boolean ready = false, running = false;
    private boolean isLandscape = false;
    private List<Library.Pack> packs;
    private int packIndex = 0;
    private TextView infoText;
    private Button orientBtn;

    private final Runnable frame = new Runnable() {
        @Override
        public void run() {
            if (running && ready) {
                renderer.draw(GlRenderer.wallSeconds(), prefs.liveEffect(), prefs.liveSpeed(), prefs.liveColor());
                if (gl != null) gl.postDelayed(this, 16); // 60 FPS
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = new Prefs(this);
        lib = new Library(this);
        packs = lib.list();
        for (int i = 0; i < packs.size(); i++) {
            if (packs.get(i).id.equals(prefs.pack())) {
                packIndex = i;
                break;
            }
        }

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(0xff0b0c10);

        SurfaceView sv = new SurfaceView(this);
        sv.getHolder().addCallback(this);
        root.addView(sv, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        // Top control panel
        LinearLayout topBar = new LinearLayout(this);
        topBar.setOrientation(LinearLayout.VERTICAL);
        topBar.setPadding(24, 48, 24, 24);
        topBar.setBackgroundColor(0xaa14161c);

        infoText = new TextView(this);
        infoText.setTextColor(0xffe8eaef);
        infoText.setTextSize(16);
        infoText.setTypeface(null, android.graphics.Typeface.BOLD);
        topBar.addView(infoText);

        LinearLayout btns = new LinearLayout(this);
        btns.setOrientation(LinearLayout.HORIZONTAL);
        btns.setPadding(0, 16, 0, 0);

        orientBtn = new Button(this);
        orientBtn.setText("Switch to Landscape");
        orientBtn.setOnClickListener(v -> toggleOrientation());
        btns.addView(orientBtn, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        Button nextBtn = new Button(this);
        nextBtn.setText("Next Wallpaper");
        nextBtn.setOnClickListener(v -> nextPack());
        btns.addView(nextBtn, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        Button closeBtn = new Button(this);
        closeBtn.setText("Close");
        closeBtn.setOnClickListener(v -> finish());
        btns.addView(closeBtn, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        topBar.addView(btns);

        FrameLayout.LayoutParams tlp = new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        tlp.gravity = Gravity.TOP;
        root.addView(topBar, tlp);

        setContentView(root);
        updateInfo();
    }

    private void updateInfo() {
        if (packs.isEmpty()) return;
        Library.Pack p = packs.get(packIndex);
        String orientName = isLandscape ? "Landscape (2408x1080)" : "Portrait (1080x2408)";
        infoText.setText(p.name + " · " + orientName + " · " + Prefs.EFFECTS[prefs.liveEffect()]);
        orientBtn.setText(isLandscape ? "Switch to Portrait" : "Switch to Landscape");
    }

    private void toggleOrientation() {
        isLandscape = !isLandscape;
        setRequestedOrientation(isLandscape ? ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE : ActivityInfo.SCREEN_ORIENTATION_PORTRAIT);
        updateInfo();
    }

    private void nextPack() {
        if (packs.isEmpty()) return;
        packIndex = (packIndex + 1) % packs.size();
        prefs.sp.edit().putString("pack", packs.get(packIndex).id).apply();
        if (gl != null) {
            gl.post(() -> {
                if (ready) renderer.loadPack(lib, packs.get(packIndex), isLandscape);
            });
        }
        updateInfo();
    }

    @Override
    public void surfaceCreated(SurfaceHolder holder) {
        thread = new HandlerThread("preview-gl");
        thread.start();
        gl = new Handler(thread.getLooper());
        gl.post(() -> {
            ready = renderer.init(holder.getSurface());
            if (ready && !packs.isEmpty()) {
                renderer.loadPack(lib, packs.get(packIndex), isLandscape);
            }
            running = true;
            frame.run();
        });
    }

    @Override
    public void surfaceChanged(SurfaceHolder holder, int format, int w, int h) {
        gl.post(() -> {
            renderer.resize(w, h);
            boolean land = w > h;
            if (land != isLandscape) {
                isLandscape = land;
                runOnUiThread(this::updateInfo);
            }
            if (ready && !packs.isEmpty()) {
                renderer.loadPack(lib, packs.get(packIndex), isLandscape);
            }
        });
    }

    @Override
    public void surfaceDestroyed(SurfaceHolder holder) {
        running = false;
        if (gl != null) {
            gl.removeCallbacks(frame);
            gl.post(() -> {
                renderer.release();
                ready = false;
            });
        }
        if (thread != null) {
            thread.quitSafely();
            thread = null;
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
    }
}
