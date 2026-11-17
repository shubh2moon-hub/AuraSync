package com.aura.phonesync;

import android.graphics.Bitmap;
import android.opengl.EGL14;
import android.opengl.EGLConfig;
import android.opengl.EGLContext;
import android.opengl.EGLDisplay;
import android.opengl.EGLSurface;
import android.opengl.GLES20;
import android.opengl.GLUtils;

/**
 * Draws a pack with an Aura effect on the GPU (OpenGL ES 2). Images are uploaded once and the
 * CPU copies are freed immediately, so the app itself holds almost no image memory.
 * The effect formulas match the PC shader (pc-app/src/aura.hlsl) and library/effects.js.
 */
final class GlRenderer {
    private static final String VS =
            "attribute vec2 p; varying vec2 uv;" +
            "void main(){ uv = vec2(p.x*0.5+0.5, 0.5-p.y*0.5); gl_Position = vec4(p,0.,1.); }";

    private static final String FS =
            "precision highp float;" +
            "varying vec2 uv; uniform sampler2D baseT; uniform sampler2D lightT;" +
            "uniform float time, speed, effect, x0, x1; uniform vec3 color; uniform vec4 crop;" +
            "vec3 hsv(float h){ h = fract(h/360.)*6.; return clamp(vec3(abs(h-3.)-1., 2.-abs(h-2.), 2.-abs(h-4.)), 0., 1.); }" +
            "vec3 fx(float x){ float t = time*speed;" +
            "  if (effect < 0.5) return color;" +
            "  if (effect < 1.5) { float k = 0.5-0.5*cos(6.2831853*t/4.); return color*(0.04+0.96*k*k); }" +
            "  if (effect < 2.5) return hsv(t*36.);" +
            "  if (effect < 3.5) { float p = fract(t*1.6); return color*(p < 0.24 ? p/0.24 : 1.-(p-0.24)/0.76); }" +
            "  if (effect < 4.5) return hsv(x*300. - t*72.);" +
            "  float q = mod(t*0.35, 1.4) - 0.2; float d = q - x;" +
            "  float k = d >= 0. ? exp(-d*d/0.02) : exp(-d*d/0.0015);" +
            "  return 0.06*color + k*color + (k > 0.85 ? (k-0.85)*2. : 0.); }" +
            "void main(){ vec2 st = crop.xy + uv*crop.zw;" +
            "  vec3 b = texture2D(baseT, st).rgb; float L = texture2D(lightT, st).r;" +
            "  vec3 o = min(b*(1.-0.55*L) + L*fx(mix(x0, x1, st.x))*0.95, 1.);" +
            "  float hot = clamp((L-0.88)/0.12, 0., 1.)*0.35; o += hot*(1.-o);" +
            "  gl_FragColor = vec4(o, 1.); }";

    private EGLDisplay display = EGL14.EGL_NO_DISPLAY;
    private EGLContext context = EGL14.EGL_NO_CONTEXT;
    private EGLSurface surface = EGL14.EGL_NO_SURFACE;
    private EGLConfig config;
    private int program, baseTex, lightTex, texW, texH;
    private int uTime, uSpeed, uEffect, uColor, uX0, uX1, uCrop;
    private int width, height;
    private int vbo = 0;
    private float x0 = 0, x1 = 1;

    boolean init(Object nativeWindow) {
        display = EGL14.eglGetDisplay(EGL14.EGL_DEFAULT_DISPLAY);
        int[] v = new int[2];
        if (!EGL14.eglInitialize(display, v, 0, v, 1)) return false;
        int[] attrs = {EGL14.EGL_RED_SIZE, 8, EGL14.EGL_GREEN_SIZE, 8, EGL14.EGL_BLUE_SIZE, 8,
                EGL14.EGL_RENDERABLE_TYPE, EGL14.EGL_OPENGL_ES2_BIT, EGL14.EGL_NONE};
        EGLConfig[] cfgs = new EGLConfig[1];
        int[] n = new int[1];
        if (!EGL14.eglChooseConfig(display, attrs, 0, cfgs, 0, 1, n, 0) || n[0] == 0) return false;
        config = cfgs[0];
        context = EGL14.eglCreateContext(display, config, EGL14.EGL_NO_CONTEXT,
                new int[]{EGL14.EGL_CONTEXT_CLIENT_VERSION, 2, EGL14.EGL_NONE}, 0);
        return setWindow(nativeWindow) && buildProgram();
    }

    boolean setWindow(Object nativeWindow) {
        if (surface != EGL14.EGL_NO_SURFACE) EGL14.eglDestroySurface(display, surface);
        surface = EGL14.eglCreateWindowSurface(display, config, nativeWindow, new int[]{EGL14.EGL_NONE}, 0);
        return surface != EGL14.EGL_NO_SURFACE && EGL14.eglMakeCurrent(display, surface, surface, context);
    }

    void resize(int w, int h) { width = w; height = h; }
    boolean isLandscape() { return width > height; }
    int getWidth() { return width; }
    int getHeight() { return height; }

    private boolean buildProgram() {
        program = GLES20.glCreateProgram();
        GLES20.glAttachShader(program, shader(GLES20.GL_VERTEX_SHADER, VS));
        GLES20.glAttachShader(program, shader(GLES20.GL_FRAGMENT_SHADER, FS));
        GLES20.glBindAttribLocation(program, 0, "p");
        GLES20.glLinkProgram(program);
        GLES20.glUseProgram(program);
        GLES20.glUniform1i(GLES20.glGetUniformLocation(program, "baseT"), 0);
        GLES20.glUniform1i(GLES20.glGetUniformLocation(program, "lightT"), 1);
        uTime = GLES20.glGetUniformLocation(program, "time");
        uSpeed = GLES20.glGetUniformLocation(program, "speed");
        uEffect = GLES20.glGetUniformLocation(program, "effect");
        uColor = GLES20.glGetUniformLocation(program, "color");
        uX0 = GLES20.glGetUniformLocation(program, "x0");
        uX1 = GLES20.glGetUniformLocation(program, "x1");
        uCrop = GLES20.glGetUniformLocation(program, "crop");

        // Use a permanent hardware Vertex Buffer Object (VBO)
        int[] bufs = new int[1];
        GLES20.glGenBuffers(1, bufs, 0);
        vbo = bufs[0];
        GLES20.glBindBuffer(GLES20.GL_ARRAY_BUFFER, vbo);
        java.nio.FloatBuffer quad = java.nio.ByteBuffer.allocateDirect(32).order(java.nio.ByteOrder.nativeOrder()).asFloatBuffer();
        quad.put(new float[]{-1, -1, 1, -1, -1, 1, 1, 1}).position(0);
        GLES20.glBufferData(GLES20.GL_ARRAY_BUFFER, 32, quad, GLES20.GL_STATIC_DRAW);
        GLES20.glBindBuffer(GLES20.GL_ARRAY_BUFFER, 0);

        int[] linked = new int[1];
        GLES20.glGetProgramiv(program, GLES20.GL_LINK_STATUS, linked, 0);
        return linked[0] != 0;
    }

    private static int shader(int type, String src) {
        int s = GLES20.glCreateShader(type);
        GLES20.glShaderSource(s, src);
        GLES20.glCompileShader(s);
        return s;
    }

    /** Uploads a pack; each bitmap is freed as soon as it is on the GPU. */
    boolean loadPack(Library lib, Library.Pack pack) {
        return loadPack(lib, pack, isLandscape());
    }

    boolean loadPack(Library lib, Library.Pack pack, boolean landscape) {
        String baseName = landscape ? "phone_land_base.jpg" : "phone_base.jpg";
        String lightName = landscape ? "phone_land_light.jpg" : "phone_light.jpg";
        Bitmap base = lib.decode(pack.id, baseName, 1);
        if (base == null && landscape) base = lib.decode(pack.id, "phone_base.jpg", 1);
        if (base == null) return false;
        texW = base.getWidth(); texH = base.getHeight();
        baseTex = upload(baseTex, base, 0);
        base.recycle();
        Bitmap light = lib.decode(pack.id, lightName, 1);
        if (light == null && landscape) light = lib.decode(pack.id, "phone_light.jpg", 1);
        if (light == null) return false;
        lightTex = uploadLuminance(lightTex, light, 1);   // 1 byte per pixel instead of 4
        light.recycle();
        x0 = landscape ? pack.landX0 : pack.x0;
        x1 = landscape ? pack.landX1 : pack.x1;
        return true;
    }

    private static int upload(int tex, Bitmap bmp, int unit) {
        if (tex == 0) {
            int[] t = new int[1];
            GLES20.glGenTextures(1, t, 0);
            tex = t[0];
        }
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0 + unit);
        GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, tex);
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR);
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR);
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE);
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE);
        GLUtils.texImage2D(GLES20.GL_TEXTURE_2D, 0, bmp, 0);
        return tex;
    }

    private static int uploadLuminance(int tex, Bitmap bmp, int unit) {
        int w = bmp.getWidth(), h = bmp.getHeight();
        java.nio.ByteBuffer bytes = java.nio.ByteBuffer.allocateDirect(w * h);
        int[] row = new int[w];
        for (int y = 0; y < h; y++) {
            bmp.getPixels(row, 0, w, 0, y, w, 1);
            for (int x = 0; x < w; x++) bytes.put((byte) (row[x] >> 16));
        }
        bytes.position(0);
        if (tex == 0) {
            int[] t = new int[1];
            GLES20.glGenTextures(1, t, 0);
            tex = t[0];
        }
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0 + unit);
        GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, tex);
        GLES20.glPixelStorei(GLES20.GL_UNPACK_ALIGNMENT, 1);
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR);
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR);
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE);
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE);
        GLES20.glTexImage2D(GLES20.GL_TEXTURE_2D, 0, GLES20.GL_LUMINANCE, w, h, 0, GLES20.GL_LUMINANCE, GLES20.GL_UNSIGNED_BYTE, bytes);
        return tex;
    }

    /** time: shared wall-clock seconds, same base as the PC so effects run in step. */
    void draw(float time, int effect, int speed, int argb) {
        if (surface == EGL14.EGL_NO_SURFACE || baseTex == 0 || program == 0) return;
        GLES20.glViewport(0, 0, width, height);

        // Bind program and configure quad vertices from hardware VBO
        GLES20.glUseProgram(program);
        GLES20.glBindBuffer(GLES20.GL_ARRAY_BUFFER, vbo);
        GLES20.glEnableVertexAttribArray(0);
        GLES20.glVertexAttribPointer(0, 2, GLES20.GL_FLOAT, false, 0, 0);

        // centre-crop the image to this surface's aspect
        float ia = texW / (float) Math.max(1, texH);
        float sa = width / (float) Math.max(1, height);
        float cw = 1, ch = 1;
        if (ia > sa) cw = sa / ia; else ch = ia / sa;
        GLES20.glUniform4f(uCrop, (1 - cw) / 2, (1 - ch) / 2, cw, ch);
        GLES20.glUniform1f(uTime, time);
        GLES20.glUniform1f(uSpeed, Prefs.SPEED_VALUES[speed]);
        GLES20.glUniform1f(uEffect, effect);
        GLES20.glUniform3f(uColor, ((argb >> 16) & 255) / 255f, ((argb >> 8) & 255) / 255f, (argb & 255) / 255f);
        GLES20.glUniform1f(uX0, x0);
        GLES20.glUniform1f(uX1, x1);

        GLES20.glActiveTexture(GLES20.GL_TEXTURE0);
        GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, baseTex);
        GLES20.glActiveTexture(GLES20.GL_TEXTURE1);
        GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, lightTex);

        GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4);

        GLES20.glBindBuffer(GLES20.GL_ARRAY_BUFFER, 0);
        EGL14.eglSwapBuffers(display, surface);
    }

    void release() {
        if (display == EGL14.EGL_NO_DISPLAY) return;
        if (vbo != 0) {
            GLES20.glDeleteBuffers(1, new int[]{vbo}, 0);
            vbo = 0;
        }
        if (baseTex != 0 || lightTex != 0) GLES20.glDeleteTextures(2, new int[]{baseTex, lightTex}, 0);
        baseTex = lightTex = 0;
        EGL14.eglMakeCurrent(display, EGL14.EGL_NO_SURFACE, EGL14.EGL_NO_SURFACE, EGL14.EGL_NO_CONTEXT);
        if (surface != EGL14.EGL_NO_SURFACE) EGL14.eglDestroySurface(display, surface);
        if (context != EGL14.EGL_NO_CONTEXT) EGL14.eglDestroyContext(display, context);
        EGL14.eglTerminate(display);
        surface = EGL14.EGL_NO_SURFACE; context = EGL14.EGL_NO_CONTEXT; display = EGL14.EGL_NO_DISPLAY;
    }

    /** Same shared clock as the PC: milliseconds within the current hour. */
    static float wallSeconds() { return effectSeconds(0); }

    /** Seconds since the shared start time (epoch ms), wrapped to an hour like the PC. */
    static float effectSeconds(long epoch) {
        long el = (System.currentTimeMillis() - epoch) % 3_600_000L;
        if (el < 0) el += 3_600_000L;
        return el / 1000f;
    }
}
