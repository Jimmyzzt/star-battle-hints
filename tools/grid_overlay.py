"""Draw 1-based row/column coordinates over a SCREENSHOT; no puzzle recognition.

Example:
 python tools/grid_overlay.py screenshot.png --rect 7 504 678 1139 -o overlay.png

--rect is left top right bottom of the OUTER GRID BORDER, in screenshot pixels.
The output is for visual checking only. Read the actual bold borders manually.
"""
import argparse
from PIL import Image, ImageDraw, ImageFont


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image')
    p.add_argument('--rect', nargs=4, type=float, required=True,
                   metavar=('LEFT','TOP','RIGHT','BOTTOM'))
    p.add_argument('--size', type=int, default=17)
    p.add_argument('-o', '--output', default='overlay.png')
    args = p.parse_args()
    image = Image.open(args.image).convert('RGB')
    l,t,r,b = args.rect
    if not (0 <= l < r <= image.width and 0 <= t < b <= image.height):
        p.error('--rect must fit within the image')
    if args.size < 2:
        p.error('--size must be >=2')
    # Overlay numbered labels on semi-transparent strips just inside the frame;
    # do not obscure the center of any cell.
    over = Image.new('RGBA', image.size, (0,0,0,0))
    d = ImageDraw.Draw(over)
    font = ImageFont.load_default()
    cell_w, cell_h = (r-l)/args.size, (b-t)/args.size
    for idx in range(args.size):
        x = int(l+(idx+.5)*cell_w)
        y = int(t+(idx+.5)*cell_h)
        txt = str(idx+1)
        d.rounded_rectangle((x-10,int(t)+1,x+10,int(t)+16), radius=2,
                            fill=(17,64,125,220))
        d.text((x,int(t)+8), txt, font=font, anchor='mm', fill='white')
        d.rounded_rectangle((int(l)+1,y-9,int(l)+22,y+9), radius=2,
                            fill=(17,64,125,220))
        d.text((int(l)+11,y), txt, font=font, anchor='mm', fill='white')
    result = Image.alpha_composite(image.convert('RGBA'),over).convert('RGB')
    result.save(args.output)
    print(args.output)


if __name__ == '__main__':
    main()
