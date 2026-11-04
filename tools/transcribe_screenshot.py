"""EXPERIMENTAL: derive region map and star/cross marks from a light-theme grid screenshot.

Unlike OCR, this uses only line thickness / center-cell color heuristics. ALWAYS
review the output against the screenshot before trusting any solver conclusion.

Example using an annotated board image:
 python tools/transcribe_screenshot.py image.jpg --rect 15 39 1353 1376 \
   --size 17 --stars-per-unit 4 -o board.json

Assumptions: straight evenly spaced grid, nearly black thick boundaries,
dark star glyphs, red X glyphs. Works best on a tightly cropped light theme.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image


def transcribe(image, rect, n, k, boundary_threshold=.36):
    rgb = np.asarray(image.convert('RGB'))
    left,top,right,bottom = rect
    dx = (right-left)/n
    dy = (bottom-top)/n
    if min(dx,dy) < 18:
        raise ValueError('cells too small for reliable scanning; enlarge screenshot first')

    def avg_dark(roi):
        if roi.size == 0:
            raise ValueError('empty sampling window; check --rect')
        return float(np.mean(np.max(roi,axis=2)<70))

    # Borders are sampled at the cell middle, away from glyphs and crossings.
    vx,hy = max(2,round(dx*.095)),max(2,round(dy*.095))
    x_margin,y_margin=max(4,round(dx*.19)),max(4,round(dy*.19))
    vertical = []
    horizontal = []
    for r in range(n):
        cy = round(top+(r+.5)*dy)
        row = []
        for c in range(n-1):
            x=round(left+(c+1)*dx)
            roi=rgb[cy-y_margin:cy+y_margin+1,x-vx:x+vx+1]
            row.append(avg_dark(roi)>boundary_threshold)
        vertical.append(row)
    for r in range(n-1):
        y=round(top+(r+1)*dy)
        row=[]
        for c in range(n):
            cx=round(left+(c+.5)*dx)
            roi=rgb[y-hy:y+hy+1,cx-x_margin:cx+x_margin+1]
            row.append(avg_dark(roi)>boundary_threshold)
        horizontal.append(row)

    # Flood fill cells across only *thin* borders.
    labels={}
    groups=[]
    for r in range(n):
        for c in range(n):
            if (r,c) in labels:
                continue
            g=len(groups)
            cells=[]
            queue=[(r,c)]
            labels[(r,c)]=g
            while queue:
                rr,cc=queue.pop()
                cells.append((rr,cc))
                for dr,dc in ((1,0),(-1,0),(0,1),(0,-1)):
                    nr,nc=rr+dr,cc+dc
                    if not (0<=nr<n and 0<=nc<n) or (nr,nc) in labels:
                        continue
                    barrier=(horizontal[min(rr,nr)][cc] if dr else
                             vertical[rr][min(cc,nc)])
                    if not barrier:
                        labels[(nr,nc)]=g
                        queue.append((nr,nc))
            groups.append(cells)
    if len(groups)!=n:
        raise ValueError(f'detected {len(groups)} regions, expected {n}; '
                         'adjust --rect and --boundary-threshold, or transcribe manually')

    # Labels for up to 50 regions. Format as arrays if labels have >1 character.
    names=[f'G{i+1}' for i in range(n)]
    regions=[[names[labels[(r,c)]] for c in range(n)] for r in range(n)]
    stars=[];crosses=[];ambiguous=[]
    w=max(4,round(min(dx,dy)*.29))
    for r in range(n):
        for c in range(n):
            x=round(left+(c+.5)*dx)
            y=round(top+(r+.5)*dy)
            roi=rgb[y-w:y+w+1,x-w:x+w+1]
            if roi.shape[:2] != (2*w+1,2*w+1):
                raise ValueError('center crop missing; recheck grid rectangle')
            a=roi.astype('int16')
            # Dark red glyph pixels only; orange highlighted backgrounds are not X marks.
            red=(a[:,:,0]>a[:,:,1]+22)&(a[:,:,0]>a[:,:,2]+18)&(a[:,:,0]>60)&(a[:,:,1]<140)&(a[:,:,2]<140)
            dark=roi.max(axis=2)<95
            dr=float(dark.mean());rr=float(red.mean())
            if dr>.15:
                stars.append([r+1,c+1])
            elif rr>.01:
                crosses.append([r+1,c+1])
            elif dr>.025 or rr>.005:
                ambiguous.append([r+1,c+1])

    return {'size':n,'stars_per_unit':k,'regions':regions,
            'stars':stars,'crosses':crosses,
            '_comment':'Auto-transcribed, experimental; CHECK every bold border and glyph against the original screenshot.',
            '_ambiguous_cells_to_review':ambiguous}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('image')
    p.add_argument('--rect',nargs=4,type=int,required=True,
                   metavar=('LEFT','TOP','RIGHT','BOTTOM'))
    p.add_argument('--size',type=int,required=True)
    p.add_argument('--stars-per-unit',type=int,required=True)
    p.add_argument('--boundary-threshold',type=float,default=.36)
    p.add_argument('-o','--output',default='transcribed.json')
    a=p.parse_args()
    im=Image.open(a.image)
    l,t,r,b=a.rect
    if not (0<=l<r<=im.width and 0<=t<b<=im.height):
        p.error('grid rect must fit inside image')
    try:
        obj=transcribe(im,(l,t,r,b),a.size,a.stars_per_unit,a.boundary_threshold)
    except ValueError as ex:
        p.error(str(ex))
    Path(a.output).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"Wrote {a.output}: {len(obj['stars'])} stars, {len(obj['crosses'])} crosses, "
          f"{len(obj['_ambiguous_cells_to_review'])} ambiguous cells. REVIEW MANUALLY.")


if __name__ == '__main__':
    main()
