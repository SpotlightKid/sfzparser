#!/usr/bin/env python
# -*- coding: utf-8 -*-

import shutil
from os.path import basename, exists, isdir, splitext

from sfzparser import SFZParser


def main(args=None):
    fn = args[0]
    bn = splitext(basename(fn))[0]
    parser = SFZParser(fn)

    fixed = False
    for name, sect in parser.sections:
        # fix sample filename without directory prefix
        if name == 'region' and 'sample' in sect and isdir(bn) and '/' not in sect['sample']:
            print("Setting prefix for sample '{}' to '{}'.".format(sect['sample'], bn))
            sect['sample'] = bn + '/' + sect['sample']
            fixed = True

    if fixed:
        if not exists(fn + '.bak'):
            shutil.copy(fn, fn + '.bak')

        with open(args[0], 'w') as sfz:
            for name, sect in parser.sections:
                if name == 'comment':
                    sfz.write(sect + '\n')
                else:
                    sfz.write("<{}>\n".format(name))
                    for key, value in sorted(sect.items()):
                        sfz.write("    {}={}\n".format(key, value))
    else:
        print("Nothing to fix.")


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:] or 0))
