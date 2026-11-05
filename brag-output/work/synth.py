"""Synthesize a 20s electronic launch bed (120 BPM) as a stereo WAV, with no
external libraries. The beat grid (0.5s) lines up with the video's scene cuts.
Intensity rises from intro -> scan -> containment peak, eases for the calm
contrast scene, resolves on the outro.
"""
import math, struct, wave

SR = 44100
DUR = 52.0
BPM = 120.0
BEAT = 60.0 / BPM            # 0.5s
N = int(SR * DUR)

def env_ad(t_in_event, attack, decay):
    if t_in_event < 0: return 0.0
    if t_in_event < attack: return t_in_event / attack
    d = t_in_event - attack
    return math.exp(-d / decay)

# A-minor progression, one chord per 5s block.
CHORDS = [
    (110.00, [220.00, 261.63, 329.63]),  # Am
    ( 87.31, [174.61, 220.00, 261.63]),  # F
    (130.81, [196.00, 261.63, 329.63]),  # C
    ( 98.00, [196.00, 246.94, 293.66]),  # G
]
def chord_at(t):
    return CHORDS[int(t // 5) % 4]   # cycle the progression across the full track

def intensity(t):
    # Sections match the video's scenes (hook, reveal, stages, scan, injection,
    # containment peak, calm contrast, extension, outro).
    for a, b, v in [(0,4,.5),(4,7.5,.72),(7.5,12,.8),(12,18.5,.9),(18.5,24,.85),
                    (24,30.5,1.0),(30.5,35,.7),(35,40,.82),(40,47,.85),(47,52,.88)]:
        if a <= t < b: base = v; break
    else: base = .8
    if t > 51.2: base *= max(0.0, (52.0 - t) / 0.8)   # outro fade
    return base

# simple deterministic noise for hats
def noise(i):
    x = math.sin(i * 12.9898) * 43758.5453
    return (x - math.floor(x)) * 2 - 1

left = [0.0] * N
right = [0.0] * N

for i in range(N):
    t = i / SR
    inten = intensity(t)
    root, triad = chord_at(t)
    beat_pos = t / BEAT
    tb = (t % BEAT)              # time since last beat
    toff = ((t + BEAT/2) % BEAT) # time since last off-beat
    s = 0.0

    # pad (always, soft) — triad sines + slight detune
    pad = 0.0
    for f in triad:
        pad += math.sin(2*math.pi*f*t) + 0.5*math.sin(2*math.pi*f*1.003*t)
    pad *= 0.06
    s += pad * (0.6 + 0.4*inten)

    # bass (from reveal) root + octave, plucked each beat
    if t >= 3:
        be = env_ad(tb, 0.005, 0.18)
        bass = (math.sin(2*math.pi*root*t) + 0.4*math.sin(2*math.pi*root*2*t)) * be
        s += bass * 0.22 * inten

    # kick (from reveal) on every beat
    if t >= 3:
        ke = env_ad(tb, 0.002, 0.12)
        pitch = 110 * math.exp(-tb*30) + 45
        s += math.sin(2*math.pi*pitch*tb) * ke * 0.5 * inten

    # hats (from scan) on off-beats, quiet
    if t >= 6:
        he = env_ad(toff, 0.001, 0.03)
        s += noise(i) * he * 0.08 * inten

    # soft saturation
    s = math.tanh(s * 1.4) * 0.8
    # tiny stereo width on pad
    left[i] = s + 0.015*math.sin(2*math.pi*0.3*t)
    right[i] = s - 0.015*math.sin(2*math.pi*0.3*t)

peak = max(1e-6, max(max(abs(x) for x in left), max(abs(x) for x in right)))
g = 0.89 / peak
with wave.open("music.wav", "w") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    frames = bytearray()
    for i in range(N):
        l = int(max(-1, min(1, left[i]*g)) * 32767)
        r = int(max(-1, min(1, right[i]*g)) * 32767)
        frames += struct.pack("<hh", l, r)
    w.writeframes(bytes(frames))
print("wrote music.wav", round(DUR,1), "s")
