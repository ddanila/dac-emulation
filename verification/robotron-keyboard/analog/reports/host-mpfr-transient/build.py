from pathlib import Path
import shutil, subprocess, os, json, hashlib, argparse
parser = argparse.ArgumentParser(description="Build isolated MPFR experiment from the verified linear-audit source")
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
root=args.out.resolve()
base=args.source.resolve()
repo=Path(__file__).resolve().parents[2]
root.mkdir(); shutil.copytree(base,root/'source'); (root/'build').mkdir()
src=root/'source'
shutil.copyfile(repo/'engine-patches/mpfr_linear_solver.h',src/'src/maths/sparse/mpfr_linear_solver.h')
patch=repo/'engine-patches/ngspice-47-mpfr-linear.patch'
with patch.open() as stream:
    subprocess.run(['patch','-p1'],cwd=src,stdin=stream,check=True)
env=os.environ.copy()
env['CPPFLAGS']=subprocess.check_output(['pkg-config','--cflags','mpfr','gmp'],text=True).strip()
env['LIBS']=subprocess.check_output(['pkg-config','--libs','mpfr','gmp'],text=True).strip()
args=[str(src/'configure'),'--prefix='+str(root/'install'),'--without-x','--with-readline=no','--disable-openmp','--disable-klu']
(root/'build-inputs.json').write_text(json.dumps({'configure':args,'CPPFLAGS':env['CPPFLAGS'],'LIBS':env['LIBS']},indent=2)+'\n')
with (root/'configure.log').open('w') as log:subprocess.run(args,cwd=root/'build',env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
with (root/'make.log').open('w') as log:subprocess.run(['make','-j4'],cwd=root/'build',env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
print(root/'build/src/ngspice')
