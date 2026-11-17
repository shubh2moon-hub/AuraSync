package com.aura.phonesync;

import android.content.Context;
import android.content.SharedPreferences;

/** What the wallpaper shows: which pack and which lighting. Shared by the wallpaper, the app and the PC link. */
final class Prefs {
    static final String NAME = "aurasync";
    static final String[] EFFECTS = {"Static", "Breathe", "Color Cycle", "Strobe", "Rainbow", "Comet"};
    static final boolean[] ANIMATED = {false, true, true, true, true, true};
    static final String[] SPEEDS = {"Slow", "Normal", "Fast"};
    static final float[] SPEED_VALUES = {0.5f, 1f, 2f};
    static final int[] COLORS = {0xffff2a3a, 0xffff6a00, 0xffffd400, 0xff2bff88, 0xff00e5ff, 0xff3d7bff, 0xff7a5cff, 0xffff2fb4, 0xffffffff};

    final SharedPreferences sp;

    Prefs(Context c) { sp = c.getApplicationContext().getSharedPreferences(NAME, Context.MODE_PRIVATE); }

    String pack() { return sp.getString("pack", "neon_horizon"); }
    boolean followPc() { return sp.getBoolean("follow_pc", true); }
    int effect() { return clamp(sp.getInt("effect", 4), 0, EFFECTS.length - 1); }
    int speed() { return clamp(sp.getInt("speed", 1), 0, 2); }
    int color() { return sp.getInt("color", COLORS[0]); }

    /** Lighting last received from the PC (used when followPc is on). */
    int pcEffect() { return clamp(sp.getInt("pc_effect", effect()), 0, EFFECTS.length - 1); }
    int pcSpeed() { return clamp(sp.getInt("pc_speed", speed()), 0, 2); }
    int pcColor() { return sp.getInt("pc_color", color()); }
    boolean hasPc() { return sp.contains("pc_effect"); }

    int liveEffect() { return followPc() && hasPc() ? pcEffect() : effect(); }
    int liveSpeed() { return followPc() && hasPc() ? pcSpeed() : speed(); }
    int liveColor() { return followPc() && hasPc() ? pcColor() : color(); }
    /** Start of the shared clock the animation counts from; 0 means this phone's own clock. */
    long liveEpoch() { return followPc() && hasPc() ? sp.getLong("pc_epoch", 0) : 0; }

    private static int clamp(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }
}
