package com.aura.phonesync;

import android.content.SharedPreferences;
import android.os.Handler;
import android.view.Choreographer;
import android.os.HandlerThread;
import android.service.wallpaper.WallpaperService;
import android.util.Log;
import android.view.SurfaceHolder;

public class AuraWallpaperService extends WallpaperService {
    private static final String TAG = "AuraWallpaper";

    @Override
    public Engine onCreateEngine() {
        return new AuraEngine();
    }

    private final class AuraEngine extends Engine implements SharedPreferences.OnSharedPreferenceChangeListener {
        private final HandlerThread thread = new HandlerThread("aura-gl");
        private Handler gl;
        private final GlRenderer renderer = new GlRenderer();
        private Library library;
        private Prefs prefs;
        private String loadedPack;
        private int lastFx = -1, lastCol;
        private boolean visible, ready;

        /** Vsync-paced: every display refresh on a 60 Hz screen, every second one on 120 Hz (60 fps, no jitter). */
        private long lastNanos;
        private boolean frameQueued;
        private final Choreographer.FrameCallback tick = new Choreographer.FrameCallback() {
            @Override public void doFrame(long nanos) {
                frameQueued = false;
                if (!visible || !ready) return;
                if (nanos - lastNanos >= 15_000_000L) {   // allow for vsync jitter around 16.7 ms
                    lastNanos = nanos;
                    draw();
                }
                if (Prefs.ANIMATED[prefs.liveEffect()]) queueFrame();
            }
        };

        private void queueFrame() {
            if (frameQueued) return;
            frameQueued = true;
            Choreographer.getInstance().postFrameCallback(tick);
        }

        /** Draws now, then keeps going frame by frame while the effect moves. */
        private final Runnable frame = new Runnable() {
            @Override public void run() {
                if (!visible || !ready) return;
                draw();
                if (Prefs.ANIMATED[prefs.liveEffect()]) queueFrame();
            }
        };

        @Override public void onCreate(SurfaceHolder holder) {
            super.onCreate(holder);
            library = new Library(AuraWallpaperService.this);
            prefs = new Prefs(AuraWallpaperService.this);
            thread.start();
            gl = new Handler(thread.getLooper());
            prefs.sp.registerOnSharedPreferenceChangeListener(this);
            Log.d(TAG, "AuraEngine onCreate");
        }

        @Override public void onSurfaceCreated(SurfaceHolder holder) {
            super.onSurfaceCreated(holder);
            gl.post(() -> {
                ready = renderer.init(holder.getSurface());
                loadedPack = null;
                Log.d(TAG, "onSurfaceCreated ready=" + ready + " visible=" + visible);
                if (ready && visible) {
                    gl.removeCallbacks(frame);
                    frame.run();
                }
            });
        }

        @Override public void onSurfaceChanged(SurfaceHolder holder, int format, int w, int h) {
            super.onSurfaceChanged(holder, format, w, h);
            gl.post(() -> {
                boolean prevLand = renderer.isLandscape();
                renderer.resize(w, h);
                Log.d(TAG, "onSurfaceChanged " + w + "x" + h + " ready=" + ready);
                if (ready) {
                    boolean land = renderer.isLandscape();
                    if (loadedPack != null && prevLand != land) {
                        Library.Pack p = library.load(prefs.pack());
                        if (p != null) renderer.loadPack(library, p, land);
                    }
                    gl.removeCallbacks(frame);
                    if (visible) {
                        frame.run();
                    } else {
                        draw();
                    }
                }
            });
        }

        @Override public void onVisibilityChanged(boolean v) {
            super.onVisibilityChanged(v);
            visible = v;
            Log.d(TAG, "onVisibilityChanged visible=" + v + " ready=" + ready);
            gl.removeCallbacks(frame);
            if (v && ready) {
                gl.post(frame);
            }
            PcLink.get(AuraWallpaperService.this).setActive(v);
        }

        @Override public void onOffsetsChanged(float xOffset, float yOffset, float xOffsetStep, float yOffsetStep, int xPixelOffset, int yPixelOffset) {
            super.onOffsetsChanged(xOffset, yOffset, xOffsetStep, yOffsetStep, xPixelOffset, yPixelOffset);
            // GL calls must run on the GL thread; the animation loop already redraws moving effects
            if (visible && ready && !Prefs.ANIMATED[prefs.liveEffect()]) gl.post(this::draw);
        }

        @Override public void onSharedPreferenceChanged(SharedPreferences sp, String key) {
            Log.d(TAG, "onSharedPreferenceChanged key=" + key);
            gl.post(() -> {
                gl.removeCallbacks(frame);
                // only a different wallpaper (or a re-synced one) needs the textures decoded again
                if ("pack".equals(key) || "pack_rev".equals(key)) loadedPack = null;
                if (visible && ready) {
                    frame.run();
                } else if (ready) {
                    draw();
                }
            });
        }

        @Override public void onSurfaceDestroyed(SurfaceHolder holder) {
            visible = false;
            ready = false;
            gl.removeCallbacks(frame);
            Log.d(TAG, "onSurfaceDestroyed");
            final Object done = new Object();
            synchronized (done) {
                gl.post(() -> {
                    renderer.release();
                    synchronized (done) { done.notify(); }
                });
                try { done.wait(2000); } catch (InterruptedException ignored) { }
            }
            super.onSurfaceDestroyed(holder);
        }

        @Override public void onDestroy() {
            prefs.sp.unregisterOnSharedPreferenceChangeListener(this);
            PcLink.get(AuraWallpaperService.this).setActive(false);
            thread.quitSafely();
            super.onDestroy();
            Log.d(TAG, "AuraEngine onDestroy");
        }

        private void draw() {
            if (!ready) return;
            boolean land = renderer.isLandscape();
            String want = prefs.pack() + "#" + prefs.sp.getInt("pack_rev", 0) + (land ? "#land" : "#port");
            if (!want.equals(loadedPack)) {
                Library.Pack p = library.load(prefs.pack());
                if (p == null) p = library.load("demon_slayer");
                if (p == null) p = library.load("neon_horizon");
                if (p != null && renderer.loadPack(library, p, land)) {
                    loadedPack = want;
                    Log.d(TAG, "Loaded wallpaper pack: " + p.id + " (landscape=" + land + ")");
                }
            }
            int fx = prefs.liveEffect(), sp = prefs.liveSpeed(), col = prefs.liveColor();
            if (fx != lastFx || col != lastCol) {
                lastFx = fx; lastCol = col;
                Log.d(TAG, "lighting effect=" + fx + " speed=" + sp + " color=" + Integer.toHexString(col)
                        + " follow=" + prefs.followPc());
            }
            renderer.draw(GlRenderer.effectSeconds(prefs.liveEpoch()), fx, sp, col);
        }
    }
}
