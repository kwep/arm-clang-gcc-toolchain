"""
Build script
"""
import util
import defs

import os
import sys
import platform
import time
from datetime import timedelta

PYVER = platform.python_version_tuple()
if int(PYVER[0]) < 3 or int(PYVER[1]) < 5:
    print('Error: This script requires Python 3.5 or later!')
    sys.exit(1)

import shutil
import argparse
import subprocess
from distutils.dir_util import copy_tree

IS_WIN = platform.system() == 'Windows'
EXT = ''
if IS_WIN:
    EXT = '.exe'

ROOT_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))

WORK_DIR = 'work'
SRC_DIR = os.path.join(WORK_DIR, 'src')
DL_DIR = os.path.join(WORK_DIR, 'dl')
BUILD_DIR = os.path.join(WORK_DIR, 'build')

DIST_DIR = 'arm-none-eabi-llvm-%s' % sys.platform
TRIPLE = 'arm-none-eabi'

ARMGCC = {}
LLVM = {}

VER = {}

CMAKE = util.which('cmake', win_defaults=defs.defpath['cmake'])
CALLENV = dict(os.environ)
CLANG = util.which('clang')
if CLANG is not None:
    CALLENV = dict(os.environ, CC='clang', CXX='clang++')

#

def missing_tool(name):
    print('Error: The %s utility is required but missing!')
    print('To install this utility on your system check the tools documentation.')
    sys.exit(1)

#

def clean(args=None):
    print('Cleaning...')
    if os.path.isdir(WORK_DIR):
        shutil.rmtree(WORK_DIR)
    if os.path.isdir(DIST_DIR):
        shutil.rmtree(DIST_DIR)

#

def download_arm_gcc():
    armgcc_link_suffix = {
        'Windows': '-win32.zip',
        'Linux': '-linux.tar.bz2',
        'Darwin': '-mac.tar.bz2'
    }[platform.system()]

    print('Fetching GNU ARM Embedded Toolchain releases...')
    armgcc_dl_link = defs.arm['base']
    for link in util.http_parse_links(defs.arm['base'] + defs.arm['dlpage'], defs.arm['link_pattern']):
        if armgcc_link_suffix in link:
            armgcc_dl_link += link
            break

    armgcc_filename = armgcc_dl_link.split('?')[0].split('/')[-1]
    armgcc_dl_link = armgcc_dl_link.replace(' ', '%20')
    armgcc_dirname = armgcc_filename.split(armgcc_link_suffix)[0]

    if os.path.isfile(armgcc_filename) is False:
        print('> Downloading "%s"... ' % armgcc_filename)
        util.download_file(armgcc_dl_link, armgcc_filename)
    else:
        print('> Latest archive "%s" already present' % armgcc_filename)

    ARMGCC['filename'] = armgcc_filename
    ARMGCC['dirname'] = armgcc_dirname

#

def download_llvm_archive(dl_link, filename):
    if os.path.isfile(filename) is False:
        print('> Downloading "%s"... ' % filename)
        util.download_file(dl_link, filename)
    else:
        print('> Latest archive "%s" already present' % filename)

#

def download_llvm():
    print('Fetching LLVM releases...')
    links = util.http_parse_links(defs.llvm['base'] + defs.llvm['dlpage'], defs.llvm['link_pattern'])

    llvm_dl_link = defs.llvm['base'] + util.match_first(links, 'llvm-')
    llvm_filename = llvm_dl_link.split('/')[-1]
    download_llvm_archive(llvm_dl_link, llvm_filename)
    LLVM['llvm'] = llvm_filename

    clang_dl_link = defs.llvm['base'] + util.match_first(links, 'cfe-')
    clang_filename = clang_dl_link.split('/')[-1]
    download_llvm_archive(clang_dl_link, clang_filename)
    LLVM['clang'] = clang_filename

    lld_dl_link = defs.llvm['base'] + util.match_first(links, 'lld-')
    lld_filename = lld_dl_link.split('/')[-1]
    download_llvm_archive(lld_dl_link, lld_filename)
    LLVM['lld'] = lld_filename

#
#
#

def download(args=None):
    print('Checking downloaded files...')
    if os.path.isdir(DL_DIR) is False:
        os.makedirs(DL_DIR)

    os.chdir(DL_DIR)

    # GNU ARM Embedded Toolchain
    download_arm_gcc()

    # LLVM+Clang sources
    download_llvm()

    os.chdir(ROOT_DIR)

#

def unpack(args=None):
    if args is not None and args.cmd == 'unpack':
        download()

    if os.path.isdir(SRC_DIR) is False:
        os.makedirs(SRC_DIR)
    if os.path.isdir(DIST_DIR) is False:
        os.makedirs(DIST_DIR)

    os.chdir(os.path.join(ROOT_DIR, SRC_DIR))

    # Unpack GNU ARM Toolchain
    if os.path.isdir(ARMGCC['dirname']) is False:
        print('> Extracting %s...' % ARMGCC['filename'])
        path = ARMGCC['dirname'] if IS_WIN else '.'
        util.extract_file(os.path.join(ROOT_DIR, DL_DIR, ARMGCC['filename']), path)

    # Copy files from GNU ARM Toolchain
    dest = DIST_DIR
    for dpath in ['include', 'lib']:
        if os.path.isdir(os.path.join(dest, TRIPLE, dpath)) is False:
            shutil.copytree(os.path.join(ARMGCC['dirname'], TRIPLE, dpath), os.path.join(dest, TRIPLE, dpath))

    if os.path.isdir(os.path.join(dest, 'lib')) is False:
        shutil.copytree(os.path.join(ARMGCC['dirname'], 'lib'), os.path.join(dest, 'lib'))

    if os.path.isdir(os.path.join(dest, 'bin')) is False:
        os.mkdir(os.path.join(dest, 'bin'))

    for bname in [
        'ar', 'as', 'gdb', 'gdb-py', 'ld', 'ld.bfd', 'nm', 'objcopy', 'objdump',
        'ranlib', 'readelf', 'size', 'strings', 'strip'
    ]:
        src = os.path.join(ARMGCC['dirname'], 'bin', '%s-%s%s' % (TRIPLE, bname, EXT))
        dst = os.path.join(dest, 'bin', bname + EXT)
        if os.path.isfile(dst) is False:
            shutil.copy2(src, dst)

    libdest = os.path.join(dest, TRIPLE, 'lib')
    gcclib = os.path.join(dest, 'lib', 'gcc', TRIPLE)
    gcclibver = os.listdir(gcclib)[0]
    VER['gcc'] = gcclibver
    if os.path.isfile(os.path.join(libdest, 'crtbegin.o')) is False:
        copy_tree(os.path.join(gcclib, gcclibver), libdest)

    cppincbase = os.path.join(dest, TRIPLE, 'include', 'c++')
    if os.path.isfile(os.path.join(cppincbase, 'algorithm')) is False:
        cppver = os.listdir(cppincbase)[0]
        src = os.path.join(cppincbase, cppver)
        util.movefiles(src, cppincbase)
        os.rmdir(src)

    # Unpack LLVM
    LLVM['src'] = LLVM['llvm'].split('.src.tar.xz')[0]
    if os.path.isdir(LLVM['src']) is False:
        print('> Extracting %s...' % LLVM['llvm'])
        util.extract_file(os.path.join(ROOT_DIR, DL_DIR, LLVM['llvm']))
        os.rename(LLVM['src'] + '.src', LLVM['src'])

    VER['llvm'] = LLVM['src'].split('-')[1]

    # Unpack Clang
    clang_tmp_dir = LLVM['clang'].split('.src.tar.xz')[0]
    clang_src_dir = os.path.join(LLVM['src'], 'tools', 'clang')
    if os.path.isdir(clang_src_dir) is False:
        print('> Extracting %s...' % LLVM['clang'])
        util.extract_file(os.path.join(ROOT_DIR, DL_DIR, LLVM['clang']))
        os.rename(clang_tmp_dir + '.src', clang_src_dir)

    # Unpack LLD
    lld_tmp_dir = LLVM['lld'].split('.src.tar.xz')[0]
    lld_src_dir = os.path.join(LLVM['src'], 'tools', 'lld')
    if os.path.isdir(lld_src_dir) is False:
        print('> Extracting %s...' % LLVM['lld'])
        util.extract_file(os.path.join(ROOT_DIR, DL_DIR, LLVM['lld']))
        os.rename(lld_tmp_dir + '.src', lld_src_dir)

    os.chdir(ROOT_DIR)

#

def configure(args=None):
    if CMAKE is None:
        missing_tool('CMake')

    if args is not None and args.cmd == 'configure':
        download()
        unpack()

    LLVM['build'] = os.path.join(BUILD_DIR, LLVM['src'])
    if os.path.isdir(LLVM['build']) is False:
        os.makedirs(LLVM['build'])

    print('Configuring sources...')

    if args is not None and args.reconfigure:
        util.rmdircontent(LLVM['build'])

    os.chdir(LLVM['build'])

    if os.path.isdir('CMakeFiles'):
        print('> LLVM is already configured')
    else:
        print('> Configuring LLVM...')
        args = [CMAKE]

        cm_gen = 'Unix Makefiles'
        if IS_WIN:
            cm_gen = 'Visual Studio 14 2015 Win64'
            args.append('-Thost=x64')

        install_dir = DIST_DIR
        args += [
            '-Wno-dev',
            '-DPYTHON_EXECUTABLE=%s' % sys.executable,
            '-DCMAKE_BUILD_TYPE=Release',
            '-DCMAKE_CROSSCOMPILING=True',
            '-DCMAKE_INSTALL_PREFIX=%s' % install_dir,
            '-DCMAKE_PREFIX_PATH=%s' % install_dir,
            '-DLLVM_INCLUDE_TESTS=OFF',
            '-DLLVM_INCLUDE_EXAMPLES=OFF',
            '-DCLANG_INCLUDE_DOCS=OFF',
            '-DLLVM_TARGETS_TO_BUILD=ARM',
            '-DLLVM_DEFAULT_TARGET_TRIPLE=%s' % TRIPLE
        ]

        if CLANG is not None:
            args.append('-DCMAKE_CXX_FLAGS=-std=c++11 -stdlib=libc++')

        args.append(os.path.join('..', '..', '..', SRC_DIR, LLVM['src']))

        exit_code = subprocess.call(args, env=CALLENV)
        if exit_code != 0:
            sys.exit(exit_code)

    os.chdir(DIST_DIR)

    with open('gcc.ver', 'w') as tfile:
        tfile.write('%s\n' % VER['gcc'])

    with open('llvm.ver', 'w') as tfile:
        tfile.write('%s\n' % VER['llvm'])

    os.chdir(ROOT_DIR)

#

def copy_extras():
    copy_tree(os.path.join(ROOT_DIR, 'extras'), DIST_DIR)
    pass

#

def build(args):
    download(args)
    unpack(args)
    configure(args)

    os.chdir(LLVM['build'])

    print('Building...')

    if os.path.isfile(os.path.join(DIST_DIR, 'bin', 'clang')) is False:
        print('> Building LLVM...')
        if IS_WIN:
            exit_code = subprocess.call([
                'MSBuild',
                'INSTALL.vcxproj',
                '/t:Build',
                '/p:Configuration=Release',
                '/m'
            ], env=CALLENV)
        else:
            exit_code = subprocess.call(['make', 'install', '-j%s' % args.jobs])

        if exit_code != 0:
            sys.exit(exit_code)

    else:
        print('> LLVM is already built')

    os.chdir(ROOT_DIR)

    copy_extras()

#
#
#

START_TS = time.time()

parser = argparse.ArgumentParser(prog='toolchain')
parser.add_argument('-p', '--prefix', help='the build destination folder path (default is "dist")')
parser.add_argument('-c', '--clean', action='store_true', help='clean the projects before executing subcommand')
parser.add_argument('-j', '--jobs', type=int, default=2, help='number of jobs used with make (default is 2)')
subparsers = parser.add_subparsers(title='subcommands', dest='cmd')

parser_build = subparsers.add_parser('build', help='build the toolchain (default)')
parser_build.add_argument('-rc', '--reconfigure', action='store_true', help='force reconfiure the target')
parser_build.add_argument('-rb', '--rebuild', action='store_true', help='force rebuild the target')
parser_build.set_defaults(func=build)

parser_clean = subparsers.add_parser('clean', help='remove build files')
parser_clean.set_defaults(func=clean)

parser_download = subparsers.add_parser('download', help='download the source files')
parser_download.set_defaults(func=download)

parser_unpack = subparsers.add_parser('unpack', help='unpack the source files')
parser_unpack.set_defaults(func=unpack)

parser_configure = subparsers.add_parser('configure', help='configure the build targets')
parser_configure.add_argument('-rc', '--reconfigure', action='store_true', help='force reconfiure the target')
parser_configure.set_defaults(func=configure)

parser.set_default_subparser('build')
args = parser.parse_args()

if args.prefix is not None:
    DIST_DIR = os.path.join(os.path.realpath(args.prefix), DIST_DIR)
else:
    DIST_DIR = os.path.join(ROOT_DIR, 'dist', DIST_DIR)

if args.clean is True:
    clean()

print('Using prefix: %s' % DIST_DIR)
args.func(args)

print('')
print('Done in', str(timedelta(seconds=time.time() - START_TS)))
