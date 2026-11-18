import json, subprocess, numpy as np
SR=48000
raw=subprocess.run(["ffmpeg","-v","error","-i","voice_el.mp3","-f","f32le","-ac","1","-ar",str(SR),"-"],capture_output=True).stdout
a=np.frombuffer(raw,np.float32)
# (segments within each line: list of (start,end, text part))
L=[[(0.0,4.876,"У тропічному лісі живе гриб, який перетворює мурах на зомбі.")],
   [(5.557,9.083,"Мураха бреде стежкою, і на неї падає крихітна спора.")],
   [(9.624,13.344,"Спора проростає крізь панцир і потрапляє всередину.")],
   [(13.853,18.591,"Гриб розростається, обплітає м'язи й поступово бере тіло під контроль.")],
   [(19.045,22.227,"Мураха кидає свою колонію і сходить зі стежки.")],
   [(22.649,26.074,"Вона залазить на рослину і спускається на нижній бік листка.")],
   [(26.419,31.347,"Там мураха щосили вчіплюється щелепами в жилку листка і більше не відпускає.")],
   [(31.790,32.916,"Вона помирає,"),(33.512,37.166,"а за кілька днів з її голови проростає довга ніжка гриба.")],
   [(37.516,39.655,"З неї вниз сиплються спори,"),(40.019,41.465,"просто на нових мурах.")],
   [(41.836,46.441,"Сліди таких укусів знайшли навіть на листі віком сорок вісім мільйонів років.")]]
B=json.load(open("beats.json"))
T=B[-1]["e"]+2.0
out=np.zeros(int(T*SR),np.float32); words=[]
for i,segs in enumerate(L):
    off=B[i]["s"]-segs[0][0]+0.05
    for s,e,txt in segs:
        s0=max(0,s-0.06); e0=e+0.12
        chunk=a[int(s0*SR):int(e0*SR)].copy()
        n=min(len(chunk),int(0.03*SR)); chunk[:n]*=np.linspace(0,1,n); chunk[-n:]*=np.linspace(1,0,n)
        p=int((s0+off)*SR); out[p:p+len(chunk)]+=chunk
        ws=txt.split(); lens=[len(w.strip(".,!?"))+1.5 for w in ws]; tot=sum(lens); acc=0
        # the first line may start with silence; find speech onset in segment
        for w,l in zip(ws,lens):
            st=s+off+(e-s)*acc/tot; acc+=l
            words.append({"w":w,"s":round(st,3),"e":round(s+off+(e-s)*acc/tot-0.02,3)})
    assert segs[-1][1]+off < (B[i+1]["s"] if i+1<len(B) else 99), i
import wave
x=(np.clip(out/np.abs(out).max()*0.9,-1,1)*32767).astype(np.int16)
w=wave.open("voice.wav","wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(x.tobytes()); w.close()
json.dump(words,open("words.json","w"),ensure_ascii=False,indent=0)
print("ok", len(words), round(len(out)/SR,2))
