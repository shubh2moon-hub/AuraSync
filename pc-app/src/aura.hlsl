// AuraSync wallpaper shader. Same formulas as library/effects.js and the phone renderer.

Texture2D<float4> BaseTex : register(t0);
Texture2D<float>  LightTex : register(t1);
SamplerState      Samp : register(s0);

cbuffer Params : register(b0) {
    float  Time;      // seconds, shared wall-clock base
    float  Speed;     // 0.5 slow, 1 normal, 2 fast
    int    Effect;    // 0 static, 1 breathe, 2 cycle, 3 strobe, 4 rainbow, 5 comet
    float  Fade;      // 0..1 cross-fade from the previous frame's colour state (unused: reserved)
    float3 Color;
    float  X0;        // scene x at the left edge of this screen
    float  X1;        // scene x at the right edge
    float3 Pad;
};

struct VSOut { float4 pos : SV_Position; float2 uv : TEXCOORD0; };

VSOut VSMain(uint id : SV_VertexID) {
    VSOut o;
    float2 uv = float2((id << 1) & 2, id & 2);
    o.uv = uv;
    o.pos = float4(uv * float2(2, -2) + float2(-1, 1), 0, 1);
    return o;
}

float3 hsv(float h) {
    h = frac(h / 360.0) * 6.0;
    float3 k = saturate(abs(h - float3(3, 2, 4)) * float3(1, -1, -1) + float3(-1, 2, 2));
    return k;
}

float3 effectColor(float x) {
    float t = Time * Speed;
    if (Effect == 1) {                    // breathe
        float k = 0.5 - 0.5 * cos(6.2831853 * t / 4.0);
        return Color * (0.04 + 0.96 * k * k);
    }
    if (Effect == 2) return hsv(t * 36.0);                       // colour cycle
    if (Effect == 3) { float p = frac(t * 1.6); return Color * (p < 0.24 ? p / 0.24 : 1.0 - (p - 0.24) / 0.76); }   // strobe: quick rise, slow fade
    if (Effect == 4) return hsv(x * 300.0 - t * 72.0);           // rainbow
    if (Effect == 5) {                    // comet
        float p = fmod(t * 0.35, 1.4) - 0.2, d = p - x;
        float k = d >= 0 ? exp(-d * d / 0.02) : exp(-d * d / 0.0015);
        return 0.06 * Color + k * Color + (k > 0.85 ? (k - 0.85) * 2.0 : 0.0);
    }
    return Color;                          // static
}

float4 PSMain(VSOut i) : SV_Target {
    float3 base = BaseTex.Sample(Samp, i.uv).rgb;
    float  L = LightTex.Sample(Samp, i.uv);
    float3 c = effectColor(lerp(X0, X1, i.uv.x));
    float3 o = min(base * (1.0 - 0.55 * L) + L * c * 0.95, 1.0);   // colour is painted over the lit area, like ASUS
    float hot = saturate((L - 0.88) / 0.12) * 0.35;
    o += hot * (1.0 - o);
    return float4(o, 1);
}
