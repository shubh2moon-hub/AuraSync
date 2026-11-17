package com.aura.phonesync;

import android.app.WallpaperManager;
import android.content.Context;
import android.graphics.Bitmap;

/**
 * Samsung lock screens can't run live wallpapers, so the lock screen gets a still image of the same
 * wallpaper lit in the current colour. Built row by row to keep memory low.
 */
final class LockScreen {
    static void apply(Context ctx) {
        Context app = ctx.getApplicationContext();
        Prefs prefs = new Prefs(app);
        Library lib = new Library(app);
        String id = prefs.pack();
        Bitmap base = lib.decode(id, "phone_base.jpg", 1);
        Bitmap light = lib.decode(id, "phone_light.jpg", 1);
        if (base == null || light == null) return;
        Bitmap out = base.copy(Bitmap.Config.ARGB_8888, true);
        base.recycle();
        int c = prefs.liveColor();
        float cr = ((c >> 16) & 255) / 255f, cg = ((c >> 8) & 255) / 255f, cb = (c & 255) / 255f;
        int w = out.getWidth(), h = out.getHeight();
        int[] row = new int[w], lrow = new int[w];
        for (int y = 0; y < h; y++) {
            out.getPixels(row, 0, w, 0, y, w, 1);
            light.getPixels(lrow, 0, w, 0, y, w, 1);
            for (int x = 0; x < w; x++) {
                float L = ((lrow[x] >> 16) & 255) / 255f;
                int p = row[x];
                float hot = Math.min(1f, Math.max(0f, (L - 0.75f) / 0.25f)) * 0.63f;
                float r = Math.min(1f, ((p >> 16) & 255) / 255f + L * cr * 1.15f);
                float g = Math.min(1f, ((p >> 8) & 255) / 255f + L * cg * 1.15f);
                float b = Math.min(1f, (p & 255) / 255f + L * cb * 1.15f);
                r += hot * (1 - r); g += hot * (1 - g); b += hot * (1 - b);
                row[x] = 0xff000000 | ((int) (r * 255) << 16) | ((int) (g * 255) << 8) | (int) (b * 255);
            }
            out.setPixels(row, 0, w, 0, y, w, 1);
        }
        light.recycle();
        try {
            WallpaperManager.getInstance(app).setBitmap(out, null, true, WallpaperManager.FLAG_LOCK);
        } catch (Exception ignored) {
        } finally {
            out.recycle();
        }
    }
}
