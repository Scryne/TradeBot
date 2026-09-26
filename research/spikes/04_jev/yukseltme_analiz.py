"""Spike 04-B: belirsiz 60 setinde veto kararı ölçümü. Etiket altin = veto | veto_degil (Claude, metin okunarak);
yukseltme_nvidia.py'nin veto_altin alanı bu sette geçersiz, burada yeniden hesaplanır.
Kullanım: python yukseltme_analiz.py data yukseltme_u60_<model>.json ...
"""
import json; import sys; import statistics;sys.stdout.reconfigure(encoding='utf-8')
d=sys.argv[1]
g={o['id']:o for o in json.load(open(f"{d}/belirsiz60_gorev.json",encoding='utf-8'))['ornekler']}
for f in sys.argv[2:]:
    s=json.load(open(f"{d}/{f}",encoding='utf-8'))
    for x in s: x['va']=g[x['id']]['altin']=='veto'
    fp=[x['id'] for x in s if x['veto_model'] and not x['va']]
    fn=[x['id'] for x in s if x['va'] and not x['veto_model']]
    su=sorted(x['sure'] for x in s if x['sure']==x['sure'])
    print(f, f"veto kararı doğru {len(s)-len(fp)-len(fn)}/{len(s)} yanlış veto {fp} kaçırılan {fn} JSON yok {sum(x['etki'] is None for x in s)} gecikme medyan {statistics.median(su):.1f} p90 {su[int(len(su)*.9)]:.1f}")
efp=[i for i,o in g.items() if o['eski_veto'] and o['altin']!='veto']; efn=[i for i,o in g.items() if not o['eski_veto'] and o['altin']=='veto']
print("eski belirsiz kural: yanlış veto", len(efp), efp, "kaçırılan", efn)
