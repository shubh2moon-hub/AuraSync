package com.aura.phonesync;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.HashMap;
import java.util.Map;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import javax.net.ssl.SSLSocketFactory;

/**
 * Connection to the AuraSync PC app through public MQTT relays (TLS), end-to-end encrypted with a key
 * derived from the pairing code. Connected only while the wallpaper (or this app) is on screen; the
 * connection is idle apart from a ping every 4 minutes, and data only flows when something changes.
 */
final class PcLink {
    private static final String[][] BROKERS = {
            {"broker.hivemq.com", "8883"}, {"broker.emqx.io", "8883"}, {"test.mosquitto.org", "8886"}};
    private static PcLink instance;

    static synchronized PcLink get(Context c) {
        if (instance == null) instance = new PcLink(c.getApplicationContext());
        return instance;
    }

    private final Context ctx;
    private final Prefs prefs;
    private final Handler main = new Handler(Looper.getMainLooper());
    private volatile boolean wanted;
    private volatile Thread thread;
    private volatile Socket socket;
    private volatile OutputStream out;
    private volatile String via;          // relay host while connected
    private volatile String pendingPack;  // wallpaper picked on the phone, to send to the PC
    private int users;

    private byte[] key;
    private String topic;
    private JSONObject packInfo;
    private final Map<Integer, byte[]> chunks = new HashMap<>();
    private boolean chunksSubscribed;

    private PcLink(Context c) {
        ctx = c;
        prefs = new Prefs(c);
        derive(prefs.sp.getString("pair_code", null));
    }

    // ------------------------------------------------------------------ public

    static String normalize(String code) {
        StringBuilder sb = new StringBuilder();
        for (char ch : code.toUpperCase().toCharArray()) if (Character.isLetterOrDigit(ch)) sb.append(ch);
        return sb.toString();
    }

    /** Saves a pairing code (10 characters from the PC's tray menu) and connects. */
    boolean pair(String code) {
        String c = normalize(code);
        if (c.length() != 10) return false;
        prefs.sp.edit().putString("pair_code", c).apply();
        derive(c);
        restart();
        return true;
    }

    boolean paired() { return key != null; }

    String pairCode() { return prefs.sp.getString("pair_code", null); }

    private volatile Runnable updateListener;
    private volatile boolean manualSyncRequested;
    private volatile boolean downloading;

    void requestUpdate(Runnable onComplete) {
        if (!paired()) {
            if (onComplete != null) onComplete.run();
            return;
        }
        manualSyncRequested = true;
        updateListener = onComplete;
        final long t0 = System.currentTimeMillis();
        main.postDelayed(new Runnable() {
            @Override public void run() {
                Runnable r = updateListener;
                if (r == null) return;
                // a wallpaper still downloading from the PC is worth waiting for (up to 40 s)
                if (downloading && System.currentTimeMillis() - t0 < 40_000) { main.postDelayed(this, 1000); return; }
                updateListener = null;
                manualSyncRequested = false;
                r.run();
            }
        }, 4000);

        new Thread(() -> {
            try {
                OutputStream o = out;
                if (o != null && topic != null) {
                    Mqtt.publish(o, topic + "/cmd", seal("cmd", "{\"sync\":1}".getBytes(StandardCharsets.UTF_8)));
                }
            } catch (Exception ignored) { }
            restart();
        }, "aura-sync-req").start();
    }

    void unpair() {
        prefs.sp.edit().remove("pair_code").apply();
        key = null;
        topic = null;
        via = null;
        stop();
    }

    String status() {
        if (!paired()) return "Not paired with a PC";
        if (via != null) return "Connected to your PC";
        long last = prefs.sp.getLong("pc_last", 0);
        if (last == 0) return "Paired, waiting for your PC";
        long min = (System.currentTimeMillis() - last) / 60000;
        return "Paired. Last update from your PC " + (min < 1 ? "just now" : min < 60 ? min + " min ago" : (min / 60) + " h ago");
    }

    /** Wallpaper and app call this while they are on screen. */
    synchronized void setActive(boolean on) {
        users = Math.max(0, users + (on ? 1 : -1));
        main.removeCallbacks(stopper);
        if (users > 0) start();
        else main.postDelayed(stopper, 20_000);   // short grace so quick app switches don't reconnect
    }

    /** Tell the PC to show this wallpaper too. */
    void sendPack(String id) {
        pendingPack = id;
        sendPending();
    }

    // ------------------------------------------------------------------ connection

    private final Runnable stopper = this::stop;

    private synchronized void start() {
        if (!paired()) return;
        wanted = true;
        if (thread == null) {
            thread = new Thread(this::loop, "aura-link");
            thread.start();
        }
    }

    private synchronized void stop() {
        wanted = false;
        closeSocket();
    }

    private void restart() {
        closeSocket();
        if (users > 0) start();
    }

    private void closeSocket() {
        try { Socket s = socket; if (s != null) s.close(); } catch (Exception ignored) { }
    }

    private void loop() {
        long backoff = 3000;
        while (wanted) {
            for (String[] b : BROKERS) {
                if (!wanted) break;
                if (session(b[0], Integer.parseInt(b[1]))) backoff = 3000;
            }
            if (!wanted) break;
            sleep(backoff);
            backoff = Math.min(backoff * 2, 120_000);
        }
        synchronized (this) { thread = null; if (wanted) start(); }
    }

    /** One connection; returns true if it got connected at all. */
    private boolean session(String host, int port) {
        String base = topic;
        try (Socket s = SSLSocketFactory.getDefault().createSocket()) {
            socket = s;
            s.connect(new InetSocketAddress(host, port), 8000);
            s.setSoTimeout(1000);
            InputStream in = s.getInputStream();
            OutputStream o = s.getOutputStream();
            Mqtt.connect(o, in, "aspp-" + Long.toHexString(new SecureRandom().nextLong()));
            Mqtt.subscribe(o, base + "/state");
            Mqtt.subscribe(o, base + "/pack/info");
            out = o;
            via = host;
            chunksSubscribed = false;
            android.util.Log.i("AuraSync", "connected to " + host);
            Mqtt.publish(o, base + "/cmd", seal("cmd", "{\"hello\":1}".getBytes(StandardCharsets.UTF_8)));
            sendPending();
            long lastPing = System.currentTimeMillis();
            while (wanted && base.equals(topic)) {
                Mqtt.Message m = Mqtt.read(in);
                if (System.currentTimeMillis() - lastPing > 240_000) { Mqtt.ping(o); lastPing = System.currentTimeMillis(); }
                if (m != null) android.util.Log.i("AuraSync", "rx " + m.topic.substring(Math.min(m.topic.length(), base.length())) + " " + m.payload.length);
                if (m == null || !m.topic.startsWith(base + "/") || m.payload.length == 0) continue;
                try { handle(m.topic.substring(base.length() + 1), m.payload, o, base); }
                catch (Exception ex) { android.util.Log.w("AuraSync", "message " + m.topic.substring(base.length() + 1) + " failed: " + ex); }
            }
            return true;
        } catch (Exception e) {
            return via != null;
        } finally {
            out = null;
            via = null;
            socket = null;
        }
    }

    private void sendPending() {
        String id = pendingPack;
        OutputStream o = out;
        if (id == null || o == null) return;
        try {
            Mqtt.publish(o, topic + "/cmd", seal("cmd", new JSONObject().put("pack", id).toString().getBytes(StandardCharsets.UTF_8)));
            pendingPack = null;
        } catch (Exception ignored) { }
    }

    // ------------------------------------------------------------------ messages

    private void handle(String name, byte[] payload, OutputStream o, String base) throws Exception {
        if (name.equals("state")) {
            JSONObject st = new JSONObject(new String(open("state", payload), StandardCharsets.UTF_8));
            String pack = st.optString("pack", "");
            android.content.SharedPreferences.Editor e = prefs.sp.edit()
                    .putInt("pc_effect", st.optInt("effect", 4))
                    .putInt("pc_speed", st.optInt("speed", 1))
                    .putInt("pc_color", 0xff000000 | st.optInt("color", 0xff2a3a))
                    .putString("pc_pack", pack)
                    .putLong("pc_last", System.currentTimeMillis())
                    .putLong("pc_epoch", st.optLong("epoch", 0));   // when the PC started this lighting, on the shared clock
            boolean packChanged = false;
            boolean shouldFollow = prefs.followPc() || manualSyncRequested;
            if (shouldFollow && !pack.isEmpty() && new Library(ctx).load(pack) != null && !pack.equals(prefs.pack())) {
                e.putString("pack", pack);
                packChanged = true;
            }
            manualSyncRequested = false;
            boolean colorChanged = prefs.pcColor() != (0xff000000 | st.optInt("color", 0xff2a3a));
            e.apply();
            android.util.Log.i("AuraSync", "state from PC via " + via + ": " + st);
            if (packChanged || colorChanged) new Thread(() -> LockScreen.apply(ctx), "aura-lock").start();
            if (updateListener != null && !downloading) {
                Runnable cb = updateListener;
                updateListener = null;
                main.post(cb);
            }
        } else if (name.equals("pack/info")) {
            packInfo = new JSONObject(new String(open("pack/info", payload), StandardCharsets.UTF_8));
            String id = packInfo.getString("id");
            if (packInfo.getString("meta").equals(localMetaHash(id))) { downloading = false; return; }   // already have it
            downloading = true;
            android.util.Log.i("AuraSync", "downloading wallpaper " + id + " from the PC: " + packInfo.optInt("size") + " bytes in " + packInfo.optInt("chunks") + " chunks");
            if (!chunksSubscribed) { Mqtt.subscribe(o, base + "/pack/+"); chunksSubscribed = true; }
            tryAssemble();
        } else if (name.startsWith("pack/")) {
            chunks.put(Integer.parseInt(name.substring(5)), payload);
            if (chunks.size() % 10 == 0) android.util.Log.i("AuraSync", "wallpaper chunks received: " + chunks.size() + " of " + (packInfo != null ? packInfo.optInt("chunks") : -1));
            tryAssemble();
        }
    }

    private String localMetaHash(String id) {
        try {
            byte[] h = MessageDigest.getInstance("SHA-256").digest(new Library(ctx).read(id, "meta.json"));
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < 8; i++) sb.append(String.format("%02x", h[i]));
            return sb.toString();
        } catch (Exception e) {
            return "";
        }
    }

    private void tryAssemble() throws Exception {
        if (packInfo == null) return;
        int n = packInfo.getInt("chunks"), size = packInfo.getInt("size");
        byte[] all = new byte[size];
        int off = 0;
        for (int i = 0; i < n; i++) {
            byte[] c = chunks.get(i);
            if (c == null || off + c.length > size) return;
            System.arraycopy(c, 0, all, off, c.length);
            off += c.length;
        }
        if (off != size) return;
        byte[] plain;
        try { plain = open("pack", all); } catch (Exception e) { return; }   // stale chunks; wait for the rest
        chunks.clear();
        install(packInfo.getString("id"), plain);
    }

    /** "ASP1" then (u16 name length, name, u32 data length, data) for meta.json, phone_base.jpg, phone_light.jpg. */
    private void install(String id, byte[] blob) throws Exception {
        ByteBuffer b = ByteBuffer.wrap(blob);
        if (b.getInt() != 0x41535031) return;
        File dir = new File(Library.syncedDir(ctx), id), tmp = new File(Library.syncedDir(ctx), id + ".tmp");
        deleteTree(tmp);
        tmp.mkdirs();
        while (b.remaining() > 6) {
            byte[] nb = new byte[b.getShort() & 0xffff];
            b.get(nb);
            String name = new File(new String(nb, StandardCharsets.UTF_8)).getName();
            byte[] data = new byte[b.getInt()];
            b.get(data);
            if (!name.equals("meta.json") && !name.equals("phone_base.jpg") && !name.equals("phone_light.jpg")
                    && !name.equals("phone_land_base.jpg") && !name.equals("phone_land_light.jpg") && !name.equals("phone_preview.jpg")) continue;
            try (FileOutputStream f = new FileOutputStream(new File(tmp, name))) { f.write(data); }
        }
        deleteTree(dir);
        if (!tmp.renameTo(dir)) return;
        prefs.sp.edit().putInt("pack_rev", prefs.sp.getInt("pack_rev", 0) + 1).apply();   // renderer reloads
        android.util.Log.i("AuraSync", "installed wallpaper " + id + " (" + blob.length + " bytes)");
        downloading = false;
        if (id.equals(prefs.sp.getString("pc_pack", "")) && (prefs.followPc() || manualSyncRequested)
                && !id.equals(prefs.pack())) {
            prefs.sp.edit().putString("pack", id).apply();
            new Thread(() -> LockScreen.apply(ctx), "aura-lock").start();
        }
        if (updateListener != null) {
            Runnable cb = updateListener;
            updateListener = null;
            main.post(cb);
        }
    }

    // ------------------------------------------------------------------ crypto

    private void derive(String code) {
        if (code == null || code.length() != 10) { key = null; topic = null; return; }
        try {
            MessageDigest d = MessageDigest.getInstance("SHA-256");
            key = d.digest(("aurasync-key:" + code).getBytes(StandardCharsets.UTF_8));
            byte[] t = MessageDigest.getInstance("SHA-256").digest(("aurasync-topic:" + code).getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder("aps2/");
            for (int i = 0; i < 10; i++) sb.append(String.format("%02x", t[i]));
            topic = sb.toString();
        } catch (Exception e) {
            key = null;
        }
    }

    private byte[] seal(String name, byte[] data) throws Exception {
        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"), new GCMParameterSpec(128, nonce));
        c.updateAAD(name.getBytes(StandardCharsets.UTF_8));
        byte[] ct = c.doFinal(data);
        byte[] o = new byte[12 + ct.length];
        System.arraycopy(nonce, 0, o, 0, 12);
        System.arraycopy(ct, 0, o, 12, ct.length);
        return o;
    }

    private byte[] open(String name, byte[] blob) throws Exception {
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"), new GCMParameterSpec(128, blob, 0, 12));
        c.updateAAD(name.getBytes(StandardCharsets.UTF_8));
        return c.doFinal(blob, 12, blob.length - 12);
    }

    private static void deleteTree(File f) {
        File[] kids = f.listFiles();
        if (kids != null) for (File k : kids) deleteTree(k);
        f.delete();
    }

    private static void sleep(long ms) { try { Thread.sleep(ms); } catch (InterruptedException ignored) { } }
}
