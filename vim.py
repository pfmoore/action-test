#!python3

import os
import re
import sys
import stat
import shutil
import hashlib
import zipfile
import tempfile
import platform
import subprocess
from configparser import ConfigParser
from pathlib import Path
from baker import Baker
from urllib.request import urlopen

HERE = os.path.dirname(os.path.abspath(__file__))

class MyBaker(Baker):
    def run_all(self, args=sys.argv):
        arg0 = args[0]
        args = args[1:]
        a = []
        for arg in args:
            if arg in self.commands:
                if a:
                    self.run(a)
                a = [arg0]
            a.append(arg)

        if a:
            self.run(a)

vim = MyBaker()

VIM_URL = "https://github.com/vim/vim.git"
SDK_DIR = "C:\\Program Files (x86)\\Microsoft SDKs\\Windows\\v7.1A\\Include"

@vim.command()
def get(target='.'):
    subprocess.check_call(['git', 'clone', VIM_URL, 'vim'], cwd=target)
    version = subprocess.check_output(
        ['git', 'describe', '--tags'],
        universal_newlines=True,
        cwd=os.path.join(target, 'vim')
    ).strip()
    if version.startswith('v'):
        version = version[1:]
    return version

@vim.command()
def patch(target='.'):
    repo = os.path.join(target, 'vim')
    cp = ConfigParser(allow_no_value=True)
    cp.read('patches/patches.ini')
    for patch, _ in cp.items('patches'):
        subprocess.check_call([
            'git', '-C', repo, 'apply',
            os.path.join('patches', patch)
        ])
        subprocess.check_call([
            'git', '-C', repo, 'commit',
            '-am', cp[patch]['message']
        ])
    

def get_vsvars(python):
    vsdevcmd = r'Program Files*\Microsoft Visual Studio\*\*\Common7\Tools\VsDevCmd.bat'
    vsdev = next(Path("C:\\").glob(vsdevcmd), None)
    if not vsdev:
        raise RuntimeError("Cannot find vsdevcmd.bat")
    return vsdev

BUILD_SCRIPT = """\
set VSCMD_VCVARSALL_INIT=1
call "{vs}" -no_logo -arch=amd64
cd vim\\src
nmake /f make_mvc.mak CPUNR=i686 WINVER=0x0501 {py} {lua} {make}
nmake /f make_mvc.mak GUI=yes DIRECTX=yes CPUNR=i686 WINVER=0x0501 {py} {lua} {make}
"""

PY = 'PYTHON{v}="{prefix}" DYNAMIC_PYTHON{v}=yes PYTHON{v}_VER={vv}'.format(
        v="" if sys.version_info[0] == 2 else "3",
        vv="{0[0]}{0[1]}".format(sys.version_info),
        prefix=sys.prefix)

@vim.command()
def build(target='.', python=True, lua=True, make=''):
    batbase = 'do_build.cmd'
    batfile = os.path.join(target, batbase)
    vs = get_vsvars(python)

    py = PY if python else ""
    lua = "LUA={here}\\lua LUA_VER=53 DYNAMIC_LUA=no".format(here=HERE) if lua else ""

    bat = BUILD_SCRIPT.format(vs=vs, py=py, lua=lua, make=make)
    with open(batfile, "w") as f:
        f.write(bat)

    subprocess.check_call(['cmd', '/c', batbase], cwd=target)

EMBEDDED_PYTHON = "https://www.python.org/ftp/python/{ver}/python-{ver}-embed-amd64.zip".format(
    ver="{0.major}.{0.minor}.{0.micro}".format(sys.version_info)
)

@vim.command()
def package(target='.', version='unknown'):
    def src(name):
        return os.path.join(target, 'vim', 'src', name)
    runtime = os.path.join(target, 'vim', 'runtime')

    version_re = re.compile('#define.*VIM_VERSION_(MAJOR|MINOR)\\s*(\\d+).*', re.S)
    ver_data = {}
    with open(src('version.h')) as f:
        for line in f:
            m = version_re.match(line)
            if m:
                ver_data[m.group(1)] = m.group(2)
    VIMRTDIR = "vim{MAJOR}{MINOR}".format_map(ver_data)

    zip_name = 'vim-{}.zip'.format(version)
    print("Writing {}".format(os.path.join(os.getcwd(), zip_name)))

    zf = zipfile.ZipFile(zip_name, 'w', compression=zipfile.ZIP_DEFLATED)
    zf.write(src('vim.exe'), 'vim.exe')
    zf.write(src('gvim.exe'), 'gvim.exe')
    zf.write(src('vimrun.exe'), 'vimrun.exe')
    zf.write(src('xxd/xxd.exe'), 'xxd.exe')
    zf.write(src('gvimext/gvimext.dll'), 'gvimext.dll')
    for dirpath, dirnames, filenames in os.walk(runtime):
        for filename in filenames:
            fullpath = os.path.join(dirpath, filename)
            zip_path = VIMRTDIR + '/' + os.path.relpath(fullpath, runtime)
            zf.write(fullpath, zip_path)
    with urlopen(EMBEDDED_PYTHON) as e:
        with open('tmp.zip', 'wb') as f:
            f.write(e.read())
        with zipfile.ZipFile('tmp.zip') as ep:
            for n in ep.namelist():
                zf.writestr('python/' + n, ep.read(n))
    zf.close()

    m = hashlib.sha256()
    m.update(Path(zip_name).read_bytes())
    print("=" * 70)
    print(f"SHA256 Hash = {m.hexdigest()}")
    print("=" * 70)
    Path(zip_name + ".sha256").write_text(m.hexdigest(), encoding="ascii")


# Copied from pip sources
def rmtree_errorhandler(func, path, exc_info):
    """On Windows, the files in .svn are read-only, so when rmtree() tries to
    remove them, an exception is thrown.  We catch that here, remove the
    read-only attribute, and hopefully continue without problems."""
    # if file type currently read only
    if os.stat(path).st_mode & stat.S_IREAD:
        # convert to read/write
        os.chmod(path, stat.S_IWRITE)
        # use the original function to repeat the operation
        func(path)
        return
    else:
        raise

@vim.command()
def all(python=True, lua=True):
    with tempfile.TemporaryDirectory() as d:
        version = get(d)
        patch(d)
        build(d, python, lua)
        package(d, version)
        # Git makes the .git subdirectory read-only,
        # so we need to delete the checkout manually
        # or the removal of the temp directory will fail.
        shutil.rmtree(os.path.join(d, 'vim'), onerror=rmtree_errorhandler)
        with open('version.txt', 'w') as f:
            f.write(version)

if __name__ == '__main__':
    for var in os.environ:
        print(var, os.environ[var])
    vim.run_all()
