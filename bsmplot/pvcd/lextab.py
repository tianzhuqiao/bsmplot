# lextab.py. This file automatically created by PLY (version 3.11). Don't edit!
_tabversion   = '3.10'
_lextokens    = set(('COMMENT', 'DATA_BINARY', 'DATA_LOGIC', 'DATA_REAL', 'DATA_STRING', 'DATE', 'DUMPALL', 'DUMPOFF', 'DUMPON', 'DUMPVARS', 'END', 'ENDDEFINITIONS', 'SCOPE', 'SPACE', 'TIMESCALE', 'UPSCOPE', 'VAR', 'VERSION', 'WORD'))
_lexreflags   = 8
_lexliterals  = ''
_lexstateinfo = {'INITIAL': 'inclusive'}
_lexstatere   = {'INITIAL': [('(?P<t_newline>\\n+)|(?P<t_DATA_LOGIC>^[01xXzZ][^\\S\\n]*)|(?P<t_DATA_BINARY>^[bB][01xXzZ]+[^\\S\\n]*)|(?P<t_DATA_REAL>^[rR][-+]?(\\d+(\\.\\d*)?|\\.\\d+)([eE][-+]?\\d+)?[^\\S\\n]*)|(?P<t_DATA_STRING>^[sS][\\S]+[^\\S\\n]*)|(?P<t_TIME>^#\\d+[^\\S\\n]*)|(?P<t_SPACE>[^\\S\\n]+)|(?P<t_WORD>\\S+)', [None, ('t_newline', 'newline'), ('t_DATA_LOGIC', 'DATA_LOGIC'), ('t_DATA_BINARY', 'DATA_BINARY'), ('t_DATA_REAL', 'DATA_REAL'), None, None, None, ('t_DATA_STRING', 'DATA_STRING'), ('t_TIME', 'TIME'), ('t_SPACE', 'SPACE'), ('t_WORD', 'WORD')])]}
_lexstateignore = {'INITIAL': ''}
_lexstateerrorf = {'INITIAL': 't_error'}
_lexstateeoff = {'INITIAL': 't_eof'}
