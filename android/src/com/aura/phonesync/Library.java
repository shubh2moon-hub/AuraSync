package com.aura.phonesync;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/**
 * Wallpaper packs. Each has phone_base.jpg (scene with lights off), phone_light.jpg (where colour goes)
 * and meta.json (name, and x0..x1: which part of the PC scene the phone shows, so effects line up).
 * Packs ship inside the app; a copy received from the PC (new framing) overrides the bundled one.
 */
final class Library {
    static final class Pack {
        final String id, name;
        final float x0, x1;
        final float landX0, landX1;
        Pack(String id, String name, float x0, float x1, float landX0, float landX1) {
            this.id = id; this.name = name;
            this.x0 = x0; this.x1 = x1;
            this.landX0 = landX0; this.landX1 = landX1;
        }
    }

    private final Context ctx;

    Library(Context c) { ctx = c.getApplicationContext(); }

    static File syncedDir(Context c) { return new File(c.getFilesDir(), "packs"); }

    List<Pack> list() {
        List<Pack> out = new ArrayList<>();
        try {
            java.util.TreeSet<String> ids = new java.util.TreeSet<>();
            String[] bundled = ctx.getAssets().list("packs");
            if (bundled != null) for (String id : bundled) ids.add(id);
            String[] synced = syncedDir(ctx).list();          // wallpapers received from the PC
            if (synced != null) for (String id : synced) if (!id.endsWith(".tmp")) ids.add(id);
            for (String id : ids) {
                Pack p = load(id);
                if (p != null) out.add(p);
            }
        } catch (Exception ignored) { }
        return out;
    }

    Pack load(String id) {
        try {
            JSONObject m = new JSONObject(new String(read(id, "meta.json"), StandardCharsets.UTF_8));
            JSONObject ph = m.optJSONObject("phone");
            float x0 = ph != null ? (float) ph.optDouble("x0", 0) : 0f;
            float x1 = ph != null ? (float) ph.optDouble("x1", 1) : 1f;
            float lx0 = ph != null ? (float) ph.optDouble("land_x0", 0) : 0f;
            float lx1 = ph != null ? (float) ph.optDouble("land_x1", 1) : 1f;
            return new Pack(id, m.optString("name", id), x0, x1, lx0, lx1);
        } catch (Exception e) {
            return null;
        }
    }

    InputStream open(String id, String file) throws Exception {
        File f = new File(new File(syncedDir(ctx), id), file);
        if (f.exists()) return new FileInputStream(f);
        return ctx.getAssets().open("packs/" + id + "/" + file);
    }

    byte[] read(String id, String file) throws Exception {
        try (InputStream in = open(id, file)) {
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            byte[] buf = new byte[16384];
            int n;
            while ((n = in.read(buf)) > 0) b.write(buf, 0, n);
            return b.toByteArray();
        }
    }

    Bitmap decode(String id, String file, int sample) { return decode(id, file, sample, false); }

    /** low=true decodes at 16 bits per pixel (half the memory; used for the on-screen scene). */
    Bitmap decode(String id, String file, int sample, boolean low) {
        BitmapFactory.Options o = new BitmapFactory.Options();
        if (low) o.inPreferredConfig = Bitmap.Config.RGB_565;
        o.inSampleSize = sample;
        o.inScaled = false;
        try (InputStream in = open(id, file)) {
            return BitmapFactory.decodeStream(in, null, o);
        } catch (Exception e) {
            return null;
        }
    }
}
