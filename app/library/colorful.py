#!/usr/bin/python3
# -*- coding: utf-8 -*-

class Colors:
    reset           = '\033[0m'

    fgBlack         = '\033[30m'
    fgBrightBlack   = '\033[30;1m'
    fgBlackLine     = '\033[30;4m'
    bgBlack         = '\033[40m'
    bgBrightBlack   = '\033[40;1m'

    fgRed           = '\033[31m'
    fgBrightRed     = '\033[31;1m'
    fgRedLine       = '\033[31;4m'
    bgRed           = '\033[41m'
    bgBrightRed     = '\033[41;1m'

    fgGreen         = '\033[32m'
    fgBrightGreen   = '\033[32;1m'
    fgGreenLine     = '\033[32;4m'
    bgGreen         = '\033[42m'
    bgBrightGreen   = '\033[42;1m'

    fgYellow        = '\033[33m'
    fgBrightYellow  = '\033[33;1m'
    fgYellowLine    = '\033[33;4m'
    bgYellow        = '\033[43m'
    bgBrightYellow  = '\033[43;1m'

    fgBlue          = '\033[34m'
    fgBrightBlue    = '\033[34;1m'
    fgBlueLine      = '\033[34;4m'
    bgBlue          = '\033[44m'
    bgBrightBlue    = '\033[44;1m'

    fgMagenta       = '\033[35m'
    fgBrightMagenta = '\033[35;1m'
    fgMagentaLine   = '\033[35;4m'
    bgMagenta       = '\033[45m'
    bgBrightMagenta = '\033[45;1m'

    fgCyan          = '\033[36m'
    fgBrightCyan    = '\033[36;1m'
    fgCyanLine      = '\033[36;4m'
    bgCyan          = '\033[46m'
    bgBrightCyan    = '\033[46;1m'

    fgWhite         = '\033[37m'
    fgBrightWhite   = '\033[37;1m'
    fgWhiteLine     = '\033[37;4m'
    bgWhite         = '\033[47m'
    bgBrightWhite   = '\033[47;1m'

LEVEL_COLOR_MAP = {
    "debug"   : f"{Colors.bgBrightMagenta}DEBUG{Colors.reset}",
    "info"    : f"{Colors.bgBrightBlue}INFO{Colors.reset}",
    "success" : f"{Colors.bgBrightGreen}SUCCESS{Colors.reset}",
    "warning" : f"{Colors.bgBrightYellow}WARNING{Colors.reset}",
    "fail"    : f"{Colors.bgBrightRed}ERROR{Colors.reset}",
    "system"  : f"{Colors.bgBrightWhite}SYSTEM{Colors.reset}"
}
