#!/usr/bin/python3
# -*- coding: utf-8 -*-

from json import loads, dumps
from os import environ, walk, getcwd
from os.path import join, isdir, splitext
from re import sub, search, finditer, findall
from argparse import ArgumentParser, RawTextHelpFormatter

try:
    from library.colorful import Colors
except ModuleNotFoundError:
    from colorful import Colors

DEAFULT_RULE = {
    "black" : [ 'fail', 'fatal', 'error', 'fault', 'bad', 'failure' ],
    "white" : [ '^#+', '^\/{2,}', 'PASS', 'Success' ],
    "match_case" : False,
    "whole_word" : False,
    "highlight"  : True,
    "enable"     : True
}

class ReportAnalyzer(object):

    def __init__(self, rule):
        self.logs   = []
        self.errors = []
        self.rule   = rule
        self.mapping()

    def __call__(self):
        if not self.ls(ARGVS.report):
            self.no_path(ARGVS.report)
        print(dumps(self.logs, indent=4))

    def no_path(self, search_path):
        print(f'\nERROR=>Report directory: {search_path} not found\n')
        exit(-1)

    def mapping(self):
        for type in ['black', 'white']:
            key = type + '_regexp'
            value = '|'.join(self.rule.get(type))
            self.__dict__[key] = value.lower()
            if self.rule.get('match_case') is True:
                self.__dict__[key] = value
            if not value:
                self.__dict__[key] = 'EmptyKeyKeep'
            if self.rule.get('whole_word') is True and type != 'white':
                self.__dict__[key] = f' ({self.__dict__[key]}) '

    def get_info(self, filename):
        with open(filename) as rf:
            lines = rf.readlines()
        return lines

    def highlight(self, regexp, string):
        if not self.rule.get('highlight'):
            return string.strip('\n')
        last_match = 0
        formatted_text = ''
        for match in finditer(regexp + r'\w+', string):
            (start, end) = match.span()
            formatted_text += string[last_match: start]
            formatted_text += Colors.fgRed
            formatted_text += string[start: end]
            formatted_text += Colors.reset
            last_match = end
        formatted_text += string[last_match:]
        return formatted_text.strip('\n')

    def ls(self, search_path='', extensions=['log', 'txt']):
        if not isdir(search_path):
            return False
        regexp = f"^{'|'.join(extensions)}$"
        ignore = 'output_action_'
        for root, dir, file in walk(search_path, topdown=False):
            for name in file:
                path = join(root, name)
                ext  = splitext(path)[-1]
                if (search(regexp, ext.lower().strip('.'))
                and not search(ignore, name)):
                    self.logs.append(path)
        return True

    def analysis(self):
        for log in self.logs:
            for line in self.get_info(log):
                if self.rule.get('match_case') is False:
                    line = line.lower()
                if search(self.white_regexp, line):
                    continue
                if not search(self.black_regexp, line):
                    continue
                self.errors.append({
                    "line"        : self.highlight(self.black_regexp, line),
                    "match_key"   : search(self.black_regexp, line).group(),
                    "match_count" : len(findall(self.black_regexp, line))
                })

    def result(self):
        return {
            "error_items"    : self.errors,
            "error_quantity" : len(self.errors),
            "status"         : ("success" if len(self.errors) == 0 else "fail"),
            "result"         : (
                "Log Analysis PASS" if len(self.errors) == 0
                else "Log Analysis FAIL"
            )
        }

def argvParser():
    global ARGVS
    parser = ArgumentParser(description='Pipeline Report Analyzer.',
                            formatter_class=RawTextHelpFormatter)
    parser.add_argument('-l', '--list',
                        action='store_true',
                        help='list files in report')
    parser.add_argument('-r', '--report',
                        dest='report', type=str,
                        default='.',
                        help='set the path of report which will be analysis')
    ARGVS = parser.parse_args()

def main():
    analyzer = ReportAnalyzer(rule=DEAFULT_RULE)
    if ARGVS.list:
        analyzer()
        exit(0)
    if not analyzer.ls(ARGVS.report):
        analyzer.no_path(ARGVS.report)
    analyzer.analysis()
    result = analyzer.result()
    print(dumps(result, indent=4))

if __name__ == '__main__':
    argvParser()
    main()
