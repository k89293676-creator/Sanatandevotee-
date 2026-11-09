import numpy as np, subprocess, sys
def make(path, seconds=30.0, sr=24000):
    rng=np.random.default_rng(3); t=np.arange(int(sr*seconds))/sr
    sig=np.zeros_like(t); pos=0.3
    while pos<seconds-1:
        d=rng.uniform(0.35,0.8); f=rng.uniform(110,190)
        i0,i1=int(pos*sr),int((pos+d)*sr)
        env=np.hanning(i1-i0)
        sig[i0:i1]+=env*(np.sin(2*np.pi*f*t[i0:i1])+0.5*np.sin(2*np.pi*2*f*t[i0:i1])+0.3*np.sin(2*np.pi*3.1*f*t[i0:i1]))*0.4
        pos+=d+rng.uniform(0.05,0.35)
    import wave
    w=wave.open(str(path)+'.wav','w'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((np.clip(sig,-1,1)*32767).astype(np.int16).tobytes()); w.close()
    subprocess.run(['ffmpeg','-y','-i',str(path)+'.wav',str(path)],capture_output=True)
