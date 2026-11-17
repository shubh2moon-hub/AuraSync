package com.aura.phonesync;

import android.app.Activity;
import android.app.WallpaperManager;
import android.content.ComponentName;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

/** Pick the wallpaper and lighting, and set it as the live wallpaper. Plain views, no preview renderer, low memory. */
public class MainActivity extends Activity {
    private static final int BG = 0xff0b0c10, PANEL = 0xff14161c, LINE = 0xff262a33, TEXT = 0xffe8eaef, MUTED = 0xff8b92a1;
    private Prefs prefs;
    private Library lib;
    private LinearLayout root;
    private final List<Bitmap> thumbs = new ArrayList<>();
    private float dp;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = new Prefs(this);
        lib = new Library(this);
        dp = getResources().getDisplayMetrics().density;
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(BG);
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(px(16), px(24), px(16), px(32));
        scroll.addView(root);
        setContentView(scroll);
        pairFromLink(getIntent());
        build();
    }

    @Override protected void onNewIntent(Intent i) {
        super.onNewIntent(i);
        if (pairFromLink(i)) build();
    }

    /** aurasync://pair/XXXXX-XXXXX pairs straight away. */
    private boolean pairFromLink(Intent i) {
        if (i == null || i.getData() == null || !"aurasync".equals(i.getData().getScheme())) return false;
        String path = i.getData().getPath();
        return path != null && PcLink.get(this).pair(path.replace("/", ""));
    }

    @Override protected void onDestroy() {
        for (Bitmap b : thumbs) b.recycle();
        thumbs.clear();
        super.onDestroy();
    }

    private void build() {
        root.removeAllViews();
        TextView title = text("AuraSync", 22, TEXT);
        title.setTypeface(null, android.graphics.Typeface.BOLD);
        root.addView(title);

        pcSyncSection();

        section("Wallpaper");
        HorizontalScrollView hs = new HorizontalScrollView(this);
        hs.setHorizontalScrollBarEnabled(false);
        LinearLayout row = new LinearLayout(this);
        hs.addView(row);
        if (thumbs.isEmpty()) for (Library.Pack p : lib.list()) thumbs.add(lib.decode(p.id, "phone_preview.jpg", 2));
        List<Library.Pack> packs = lib.list();
        for (int i = 0; i < packs.size(); i++) {
            Library.Pack p = packs.get(i);
            LinearLayout card = new LinearLayout(this);
            card.setOrientation(LinearLayout.VERTICAL);
            card.setPadding(px(4), px(4), px(4), px(6));
            boolean sel = p.id.equals(prefs.pack());
            card.setBackground(box(sel ? 0xff2a2f3b : PANEL, sel ? 0xffffffff : LINE, 10));
            ImageView iv = new ImageView(this);
            if (i < thumbs.size() && thumbs.get(i) != null) iv.setImageBitmap(thumbs.get(i));
            iv.setScaleType(ImageView.ScaleType.CENTER_CROP);
            card.addView(iv, new LinearLayout.LayoutParams(px(96), px(214)));
            TextView name = text(p.name, 12, TEXT);
            name.setGravity(Gravity.CENTER);
            card.addView(name, new LinearLayout.LayoutParams(px(96), ViewGroup.LayoutParams.WRAP_CONTENT));
            card.setContentDescription(p.name + (sel ? ", selected" : ""));
            card.setOnClickListener(v -> {
                prefs.sp.edit().putString("pack", p.id).apply();
                if (PcLink.get(this).paired()) PcLink.get(this).sendPack(p.id);   // the PC switches too
                build();
            });
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            lp.rightMargin = px(10);
            row.addView(card, lp);
        }
        root.addView(hs);

        section("Lighting");
        boolean follow = prefs.followPc();
        root.addView(chipRow(new String[]{"Follow my PC", "Choose here"}, follow ? 0 : 1, i -> {
            prefs.sp.edit().putBoolean("follow_pc", i == 0).apply(); build(); }));
        if (follow) {
            root.addView(text(prefs.hasPc()
                    ? "Using the PC's lighting: " + Prefs.EFFECTS[prefs.pcEffect()] + ". Until the PC is linked, it uses the effect below."
                    : "No lighting from the PC yet, so the effect below is used.", 12, MUTED));
        }
        root.addView(chipRow(Prefs.EFFECTS, prefs.effect(), i -> { prefs.sp.edit().putInt("effect", i).apply(); build(); }));
        section("Speed");
        root.addView(chipRow(Prefs.SPEEDS, prefs.speed(), i -> { prefs.sp.edit().putInt("speed", i).apply(); build(); }));
        section("Color");
        LinearLayout sw = new LinearLayout(this);
        for (int c : Prefs.COLORS) {
            View d = new View(this);
            boolean sel = c == prefs.color();
            GradientDrawable g = new GradientDrawable();
            g.setShape(GradientDrawable.OVAL);
            g.setColor(c);
            g.setStroke(px(2), sel ? 0xffffffff : 0x00000000);
            d.setBackground(g);
            d.setContentDescription(String.format("Color #%06X%s", c & 0xffffff, sel ? ", selected" : ""));
            d.setOnClickListener(v -> { prefs.sp.edit().putInt("color", c).apply(); build(); });
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(px(32), px(32));
            lp.rightMargin = px(8);
            sw.addView(d, lp);
        }
        root.addView(sw);

        Button preview = new Button(this);
        preview.setText("Live Simulator / Test Orientations");
        preview.setAllCaps(false);
        preview.setTextColor(TEXT);
        preview.setBackground(box(PANEL, LINE, 8));
        preview.setOnClickListener(v -> startActivity(new Intent(this, PreviewActivity.class)));
        LinearLayout.LayoutParams plp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(48));
        plp.topMargin = px(24);
        root.addView(preview, plp);

        Button set = new Button(this);
        set.setText("Set as wallpaper");
        set.setAllCaps(false);
        set.setTextColor(BG);
        set.setBackground(box(TEXT, TEXT, 8));
        set.setOnClickListener(v -> apply());
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(48));
        lp.topMargin = px(12);
        root.addView(set, lp);
        root.addView(text("Sets the live wallpaper on the home screen and a matching still image on the lock screen.", 12, MUTED));
    }

    private TextView status;
    private int shownRev = -1;
    private String shownPack;
    private final android.os.Handler ui = new android.os.Handler();
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            if (status != null) {
                PcLink link = PcLink.get(MainActivity.this);
                status.setText(link.status());
                status.setTextColor(link.paired() ? 0xff4ade80 : MUTED);
            }
            // a wallpaper arrived from the PC, or the PC changed the pick: redraw the list
            int rev = prefs.sp.getInt("pack_rev", 0);
            String pk = prefs.pack();
            if (rev != shownRev || !pk.equals(shownPack)) {
                shownRev = rev; shownPack = pk;
                for (Bitmap b : thumbs) if (b != null) b.recycle();
                thumbs.clear();
                build();
            }
            ui.postDelayed(this, 2000);
        }
    };

    @Override protected void onResume() {
        super.onResume();
        PcLink.get(this).setActive(true);
        ui.post(refresh);
    }

    /** The wallpaper keeps running after this screen is hidden, so give back all the screen's memory. */
    @Override protected void onStop() {
        root.removeAllViews();
        for (Bitmap b : thumbs) if (b != null) b.recycle();
        thumbs.clear();
        super.onStop();
    }

    @Override protected void onRestart() {
        super.onRestart();
        build();
    }

    @Override protected void onPause() {
        ui.removeCallbacks(refresh);
        PcLink.get(this).setActive(false);
        super.onPause();
    }

    private void pcSyncSection() {
        section("PC Sync & Pairing");
        PcLink link = PcLink.get(this);
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackground(box(PANEL, LINE, 10));
        card.setPadding(px(14), px(12), px(14), px(14));

        status = text(link.status(), 14, link.paired() ? 0xff4ade80 : MUTED);
        status.setTypeface(null, android.graphics.Typeface.BOLD);
        card.addView(status);

        if (link.paired()) {
            String pCode = link.pairCode();
            if (pCode != null && pCode.length() == 10) {
                pCode = pCode.substring(0, 5) + "-" + pCode.substring(5);
            }
            TextView codeInfo = text("Paired code: " + (pCode != null ? pCode : "Active"), 12, MUTED);
            codeInfo.setPadding(0, px(4), 0, px(10));
            card.addView(codeInfo);

            LinearLayout btnRow = new LinearLayout(this);
            btnRow.setOrientation(LinearLayout.HORIZONTAL);

            Button unpairBtn = new Button(this);
            unpairBtn.setText("Unpair / Switch PC");
            unpairBtn.setAllCaps(false);
            unpairBtn.setTextSize(13);
            unpairBtn.setTextColor(TEXT);
            unpairBtn.setBackground(box(0xff2a2f3b, LINE, 6));
            unpairBtn.setOnClickListener(v -> {
                link.unpair();
                build();
            });
            LinearLayout.LayoutParams ubLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, px(36));
            ubLp.rightMargin = px(8);
            btnRow.addView(unpairBtn, ubLp);

            Button updateBtn = new Button(this);
            updateBtn.setText("Update now");
            updateBtn.setAllCaps(false);
            updateBtn.setTextSize(13);
            updateBtn.setTextColor(BG);
            updateBtn.setBackground(box(TEXT, TEXT, 6));
            updateBtn.setOnClickListener(v -> {
                updateBtn.setText("Updating...");
                updateBtn.setEnabled(false);
                link.requestUpdate(() -> {
                    updateBtn.setText("Update now");
                    updateBtn.setEnabled(true);
                    build();
                    android.widget.Toast.makeText(this, "Wallpaper synced with PC", android.widget.Toast.LENGTH_SHORT).show();
                });
            });
            LinearLayout.LayoutParams upLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, px(36));
            btnRow.addView(updateBtn, upLp);

            card.addView(btnRow);
        } else {
            TextView guide = text("To pair with your PC, right-click the AuraSync tray icon on your PC, choose \"Pair phone\", and type the 10-character code below:", 12, MUTED);
            guide.setPadding(0, px(4), 0, px(10));
            card.addView(guide);

            LinearLayout row = new LinearLayout(this);
            row.setGravity(Gravity.CENTER_VERTICAL);

            android.widget.EditText code = new android.widget.EditText(this);
            code.setHint("XXXXX-XXXXX");
            code.setHintTextColor(0xff5c6370);
            code.setTextColor(TEXT);
            code.setTextSize(14);
            code.setSingleLine(true);
            code.setBackground(box(BG, LINE, 6));
            code.setPadding(px(12), px(8), px(12), px(8));
            code.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
                    | android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
            code.setContentDescription("Pairing code");
            LinearLayout.LayoutParams clp = new LinearLayout.LayoutParams(0, px(42), 1);
            clp.rightMargin = px(10);
            row.addView(code, clp);

            Button go = new Button(this);
            go.setText("Pair");
            go.setAllCaps(false);
            go.setTextSize(13);
            go.setTextColor(BG);
            go.setBackground(box(TEXT, TEXT, 6));
            go.setOnClickListener(v -> {
                if (link.pair(code.getText().toString())) build();
                else code.setError("The code has 10 letters and numbers");
            });
            row.addView(go, new LinearLayout.LayoutParams(px(80), px(42)));
            card.addView(row);
        }

        root.addView(card);
    }

    private void apply() {
        new Thread(() -> LockScreen.apply(this), "aura-lock").start();
        Intent i = new Intent(WallpaperManager.ACTION_CHANGE_LIVE_WALLPAPER);
        i.putExtra(WallpaperManager.EXTRA_LIVE_WALLPAPER_COMPONENT, new ComponentName(this, AuraWallpaperService.class));
        try { startActivity(i); } catch (Exception e) { startActivity(new Intent(WallpaperManager.ACTION_LIVE_WALLPAPER_CHOOSER)); }
    }

    // ---- small view helpers

    interface Pick { void on(int i); }

    private LinearLayout chipRow(String[] labels, int selected, Pick pick) {
        LinearLayout wrap = new LinearLayout(this);
        wrap.setOrientation(LinearLayout.VERTICAL);
        LinearLayout row = null;
        for (int i = 0; i < labels.length; i++) {
            if (i % 3 == 0) {
                row = new LinearLayout(this);
                LinearLayout.LayoutParams rl = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
                rl.bottomMargin = px(6);
                wrap.addView(row, rl);
            }
            TextView chip = text(labels[i], 14, TEXT);
            chip.setGravity(Gravity.CENTER);
            chip.setPadding(px(12), px(8), px(12), px(8));
            chip.setBackground(box(i == selected ? 0xff2a2f3b : PANEL, i == selected ? 0xff6b7385 : LINE, 6));
            chip.setContentDescription(labels[i] + (i == selected ? ", selected" : ""));
            final int idx = i;
            chip.setOnClickListener(v -> pick.on(idx));
            LinearLayout.LayoutParams cl = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
            cl.rightMargin = px(6);
            row.addView(chip, cl);
        }
        return wrap;
    }

    private void section(String s) {
        TextView t = text(s.toUpperCase(), 12, MUTED);
        t.setPadding(0, px(20), 0, px(8));
        t.setLetterSpacing(0.08f);
        root.addView(t);
    }

    private TextView text(String s, int sp, int color) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        return t;
    }

    private GradientDrawable box(int fill, int stroke, int radius) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(fill);
        g.setStroke(px(1), stroke);
        g.setCornerRadius(px(radius));
        return g;
    }

    private int px(float v) { return (int) (v * dp + 0.5f); }
}
