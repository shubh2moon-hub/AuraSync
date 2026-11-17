package com.aura.phonesync;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;

/** Just enough MQTT 3.1.1 for a short check-in: connect, subscribe, QoS 0 publish, read. */
final class Mqtt {
    static final class Message {
        final String topic;
        final byte[] payload;
        Message(String t, byte[] p) { topic = t; payload = p; }
    }

    static void connect(OutputStream out, InputStream in, String clientId) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        str(b, "MQTT");
        b.write(4);          // protocol level 3.1.1
        b.write(0x02);       // clean session
        b.write(1); b.write(44);   // keep-alive 300 s: the link pings every 4 minutes
        str(b, clientId);
        send(out, 0x10, b.toByteArray());
        long until = System.currentTimeMillis() + 8000;
        while (System.currentTimeMillis() < until) {
            try {
                int type = in.read();
                if (type < 0) throw new IOException("closed");
                byte[] body = readFully(in, remaining(in));
                if ((type & 0xF0) == 0x20) {
                    if (body.length < 2 || body[1] != 0) throw new IOException("refused");
                    return;
                }
            } catch (SocketTimeoutException ignored) { }
        }
        throw new IOException("no CONNACK");
    }

    static void subscribe(OutputStream out, String topic) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        b.write(0); b.write(1);
        str(b, topic);
        b.write(0);
        send(out, 0x82, b.toByteArray());
    }

    static void publish(OutputStream out, String topic, byte[] payload) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        str(b, topic);
        b.write(payload);
        send(out, 0x30, b.toByteArray());
    }

    static void ping(OutputStream out) throws IOException { send(out, 0xC0, new byte[0]); }

    static void disconnect(OutputStream out) {
        try { send(out, 0xE0, new byte[0]); } catch (IOException ignored) { }
    }

    /** Next PUBLISH, or null on a read timeout / non-publish packet. */
    static Message read(InputStream in) throws IOException {
        int type;
        try {
            type = in.read();
        } catch (SocketTimeoutException e) {
            return null;
        }
        if (type < 0) throw new IOException("closed");
        byte[] body = readFully(in, remaining(in));
        if ((type & 0xF0) != 0x30) return null;
        int tl = ((body[0] & 0xFF) << 8) | (body[1] & 0xFF);
        int qos = (type >> 1) & 3;
        int off = 2 + tl + (qos > 0 ? 2 : 0);
        byte[] payload = new byte[body.length - off];
        System.arraycopy(body, off, payload, 0, payload.length);
        return new Message(new String(body, 2, tl, StandardCharsets.UTF_8), payload);
    }

    private static int remaining(InputStream in) throws IOException {
        int mult = 1, len = 0, b;
        do {
            b = readByte(in);
            len += (b & 0x7F) * mult;
            mult *= 128;
        } while ((b & 0x80) != 0);
        return len;
    }

    private static int readByte(InputStream in) throws IOException {
        while (true) {
            try {
                int b = in.read();
                if (b < 0) throw new IOException("closed");
                return b;
            } catch (SocketTimeoutException ignored) { }
        }
    }

    private static byte[] readFully(InputStream in, int n) throws IOException {
        byte[] buf = new byte[n];
        int off = 0;
        while (off < n) {
            try {
                int r = in.read(buf, off, n - off);
                if (r < 0) throw new IOException("closed");
                off += r;
            } catch (SocketTimeoutException ignored) { }
        }
        return buf;
    }

    private static void send(OutputStream out, int header, byte[] body) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        b.write(header);
        int n = body.length;
        do {
            int d = n % 128;
            n /= 128;
            b.write(n > 0 ? d | 0x80 : d);
        } while (n > 0);
        b.write(body);
        synchronized (out) {
            out.write(b.toByteArray());
            out.flush();
        }
    }

    private static void str(ByteArrayOutputStream b, String s) throws IOException {
        byte[] d = s.getBytes(StandardCharsets.UTF_8);
        b.write(d.length >> 8);
        b.write(d.length & 0xFF);
        b.write(d);
    }
}
