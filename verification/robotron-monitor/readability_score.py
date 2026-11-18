"""Score one native CRT frame against logical VIDEO with one global affine fit.

The affine transform is determined by the two images' intensity moments. It is
used only to sample the rendered image for scoring, never to modify the render.
"""
import array
import hashlib
import json
import math
from pathlib import Path
import sys


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def read_archive(directory):
    root=Path(directory).resolve()
    report=json.loads((root/'frame.json').read_text())
    if report.get('format')!='dac-periodic-frame-v1' or report.get('status')!='complete':
        raise ValueError('G8 requires a complete periodic optical archive')
    if 'input.csv' not in report.get('hashes',{}):
        raise ValueError('G8 optical archive lacks its electrical input')
    for name,expected in report.get('hashes',{}).items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or _digest(path)!=expected:
            raise ValueError('G8 optical input or model hash mismatch')
    output=report.get('outputs',{}).get('frame.f32',{})
    path=(root/output.get('path','')).resolve()
    if not path.is_relative_to(root) or _digest(path)!=output.get('sha256'):
        raise ValueError('G8 linear frame hash mismatch')
    fmt=report.get('linear_format',{})
    width,height=fmt.get('width'),fmt.get('height')
    if (fmt.get('dtype')!='little-endian float32' or fmt.get('order')!='row-major'
            or type(width) is not int or type(height) is not int
            or not 16<=width<=2048 or not 16<=height<=2048 or width*height>1048576
            or report.get('render',{}).get('parameters',{}).get('width')!=width
            or report.get('render',{}).get('parameters',{}).get('height')!=height):
        raise ValueError('G8 linear frame dimensions or format mismatch')
    raw=path.read_bytes()
    if len(raw)!=4*width*height:
        raise ValueError('G8 linear frame size mismatch')
    pixels=array.array('f');pixels.frombytes(raw)
    if sys.byteorder!='little':pixels.byteswap()
    if any(not math.isfinite(v) or v<0 for v in pixels) or not any(pixels):
        raise ValueError('G8 linear frame is invalid or dark')
    return width,height,pixels


def _moments(values,width,height):
    total=sx=sy=sxx=sxy=syy=0.
    for row in range(height):
        y=(row+.5)/height
        for col in range(width):
            weight=values[row*width+col]
            if weight<=0:continue
            x=(col+.5)/width
            total+=weight;sx+=weight*x;sy+=weight*y
            sxx+=weight*x*x;sxy+=weight*x*y;syy+=weight*y*y
    if not math.isfinite(total) or total<=0:raise ValueError('G8 image has no finite positive signal')
    mx,my=sx/total,sy/total
    covariance=(sxx/total-mx*mx,sxy/total-mx*my,syy/total-my*my)
    if covariance[0]<=1e-5 or covariance[2]<=1e-5 or covariance[0]*covariance[2]-covariance[1]**2<=1e-10:
        raise ValueError('G8 image lacks two-dimensional extent')
    return (mx,my),covariance


def _multiply(a,b):
    return ((a[0][0]*b[0][0]+a[0][1]*b[1][0],a[0][0]*b[0][1]+a[0][1]*b[1][1]),
            (a[1][0]*b[0][0]+a[1][1]*b[1][0],a[1][0]*b[0][1]+a[1][1]*b[1][1]))


def _inverse(a):
    determinant=a[0][0]*a[1][1]-a[0][1]*a[1][0]
    if not math.isfinite(determinant) or determinant<=1e-12:
        raise ValueError('G8 affine fit is singular')
    return ((a[1][1]/determinant,-a[0][1]/determinant),
            (-a[1][0]/determinant,a[0][0]/determinant))


def _sqrt_spd(covariance):
    xx,xy,yy=covariance
    determinant=xx*yy-xy*xy
    if determinant<=0:raise ValueError('G8 covariance is not positive definite')
    d=math.sqrt(determinant)
    scale=math.sqrt(xx+yy+2*d)
    return (( (xx+d)/scale,xy/scale),(xy/scale,(yy+d)/scale))


def _reference(logical,width,height):
    target_width=min(216,width);target_height=min(156,height)
    values=[]
    for row in range(target_height):
        y0=row*height//target_height;y1=(row+1)*height//target_height
        for col in range(target_width):
            x0=col*width//target_width;x1=(col+1)*width//target_width
            values.append(sum(logical[y*width+x] for y in range(y0,y1) for x in range(x0,x1))
                          /(255*(y1-y0)*(x1-x0)))
    return target_width,target_height,values


def _sample(pixels,width,height,x,y):
    col=x*width-.5;row=y*height-.5
    if col<0 or row<0 or col>width-1 or row>height-1:return 0.
    x0=int(col);y0=int(row);x1=min(width-1,x0+1);y1=min(height-1,y0+1)
    fx=col-x0;fy=row-y0
    return ((1-fy)*((1-fx)*pixels[y0*width+x0]+fx*pixels[y0*width+x1])
            +fy*((1-fx)*pixels[y1*width+x0]+fx*pixels[y1*width+x1]))


def correlate(logical,width,height,rendered,render_width,render_height):
    if (len(logical)!=width*height or len(rendered)!=render_width*render_height
            or any(not math.isfinite(v) or v<0 for v in rendered)):
        raise ValueError('G8 image dimensions or pixels are invalid')
    rw,rh,reference=_reference(logical,width,height)
    image_peak=max(rendered)
    if image_peak<=0:raise ValueError('G8 dark frame cannot establish readability')
    normalized=array.array('d',(value/image_peak for value in rendered))
    logical_center,logical_cov=_moments(reference,rw,rh)
    image_center,image_cov=_moments(normalized,render_width,render_height)
    image_sqrt=_sqrt_spd(image_cov)
    middle=_multiply(_multiply(image_sqrt,((logical_cov[0],logical_cov[1]),
                                          (logical_cov[1],logical_cov[2]))),image_sqrt)
    affine=_multiply(_multiply(_inverse(image_sqrt),_sqrt_spd(
        (middle[0][0],middle[0][1],middle[1][1]))),_inverse(image_sqrt))
    inverse=_inverse(affine)
    n=rw*rh;sum_a=sum_b=sum_aa=sum_bb=sum_ab=0.
    for row in range(rh):
        y=(row+.5)/rh
        for col in range(rw):
            x=(col+.5)/rw
            dx=x-logical_center[0];dy=y-logical_center[1]
            a=reference[row*rw+col]
            b=0.
            for oy in (-1/3,0,1/3):
                for ox in (-1/3,0,1/3):
                    sub_x=dx+ox/rw;sub_y=dy+oy/rh
                    ix=image_center[0]+inverse[0][0]*sub_x+inverse[0][1]*sub_y
                    iy=image_center[1]+inverse[1][0]*sub_x+inverse[1][1]*sub_y
                    b+=_sample(normalized,render_width,render_height,ix,iy)/9
            sum_a+=a;sum_b+=b;sum_aa+=a*a;sum_bb+=b*b;sum_ab+=a*b
    covariance=sum_ab-sum_a*sum_b/n
    variance_a=sum_aa-sum_a*sum_a/n;variance_b=sum_bb-sum_b*sum_b/n
    if variance_a<=0 or variance_b<=0:raise ValueError('G8 correlation has zero variance')
    correlation=covariance/math.sqrt(variance_a*variance_b)
    if not math.isfinite(correlation):raise ValueError('G8 correlation is not finite')
    return dict(correlation=max(-1.,min(1.,correlation)),
                method='single-global-intensity-moment-affine-and-pearson',
                one_global_affine_fit=True,fit_applied_to_render=False,
                affine_image_to_logical=[list(row) for row in affine],
                image_center=list(image_center),logical_center=list(logical_center),
                scoring_grid=[rw,rh])


def score(selection,archive):
    import scan_diagnostics
    reference,logical=scan_diagnostics.source_summary(selection)
    width,height,pixels=read_archive(archive)
    result=correlate(logical,reference['width'],reference['height'],pixels,width,height)
    result.update(source_kind='native-firmware-logical-timing-reference',
                  source_content_sha256=selection['source_content_sha256'],
                  render_manifest_sha256=_digest(Path(archive)/'frame.json'))
    return result
